import assert from "node:assert"
import {
  readFile,
  writeFile,
  mkdir,
  copyFile,
  chown,
  chmod,
} from "node:fs/promises"
import { join } from "node:path"
import { fileURLToPath } from "node:url"

import { $ } from "execa"
import { stringify, parse } from "ini"
import dedent from "dedent"

import {
  getBlockDevices,
  backupAndReplace,
  backupAndRemove,
  getMountPoint,
} from "./lib.js"

export async function createPartitions(device, rpios_partitions) {
  // We create the entire partition table first
  // so that a fs can be resized to fill remaining space
  // until next partition - for example with resize2fs
  await createPartitionTable(device)

  const partitions = await getPartitions(device)

  await create_bootloaderfs(partitions["BOOTLOADER"])

  const rpios_bootfs = rpios_partitions["bootfs"]
  await create_firmwarefs(partitions["FIRMWARE A"], rpios_bootfs)
  await create_firmwarefs(partitions["FIRMWARE B"], rpios_bootfs)

  const rpios_rootfs = rpios_partitions["rootfs"]
  await create_rootfs(partitions["ROOT A"], rpios_rootfs)
  await create_rootfs(partitions["ROOT B"], rpios_rootfs)

  await create_datafs(partitions["DATA"])
}

export async function updateMountpoints(device, rpios_partitions) {
  const partitions = await getPartitions(device)

  await setup_cmdline(rpios_partitions, partitions)
  await setup_config(rpios_partitions, partitions)
  await setup_cloudinit(rpios_partitions, partitions)
  await setup_fstab(partitions)
  await setup_autoboot(partitions)
}

async function createPartitionTable(device) {
  // Removes existing GPT/MBR data.
  await $`sgdisk --zap-all ${device}`

  // Create a new partition table
  await $`sgdisk --new ${device}`

  // 0 is "Platform required"
  // 1 is "EFI firmware should ignore the content"
  // 62 is "Hidden"
  // 63 is "No drive letter (i.e. do not automount) "
  // See https://en.wikipedia.org/wiki/GUID_Partition_Table#Partition_entries_(LBA_2%E2%80%9333)

  // # Partition 1: 8MB FAT12 "BOOTLOADER"
  await $`sgdisk --new=1:0:+8M --typecode=1:0700 -A 1:set:0 -A 1:set:1 -A 1:set:62 -A 1:set:63 --change-name=1:BOOTLOADER ${device}`
  // # Partition 2: 236MB FAT32 "FIRMWARE A"
  await $`sgdisk --new=2:0:+256M --typecode=2:0700 -A 2:set:0 -A 2:set:1 -A 2:set:62 -A 2:set:63 --change-name=2:${"FIRMWARE A"} ${device}`
  // # Partition 3: 236MB FAT32 "FIRMWARE B"
  await $`sgdisk --new=3:0:+256M --typecode=3:0700 -A 3:set:0 -A 3:set:1 -A 3:set:62 -A 3:set:63 --change-name=3:${"FIRMWARE B"} ${device}`
  // # Partition 4: 10GB EXT4 "ROOT A"
  await $`sgdisk --new=4:0:+10G --typecode=4:8300 -A 4:set:0 -A 4:set:1 -A 4:set:62 -A 4:set:63 --change-name=4:${"ROOT A"} ${device}`
  // # Partition 5: 10GB EXT4 "ROOT B"
  await $`sgdisk --new=5:0:+10G --typecode=5:8300 -A 5:set:0 -A 5:set:1 -A 5:set:62 -A 5:set:63 --change-name=5:${"ROOT B"} ${device}`
  // # Partition 6: Remaining space EXT4 "DATA"
  await $`sgdisk --new=6:0:0 --typecode=6:8300 -A 6:set:0 -A 6:set:1  -A 6:set:62 -A 6:set:63 --change-name=6:DATA ${device}`

  await $`sgdisk --verify ${device}`

  // Inform kernel of partition table changes
  await $`partprobe ${device}`
  // Inform userspace of partition table changes
  await $`udevadm settle`
}

async function create_bootloaderfs({ partlabel, path }) {
  const mountpoint = await getMountPoint(partlabel)
  await $`wipefs -a ${path}`
  await $`mkfs.vfat -F12 ${path} -n ${partlabel}`
  await $`mount ${path} ${mountpoint}`
  await $`cp autoboot.ini ${join(mountpoint, "autoboot.txt")}`
}

async function create_firmwarefs({ path, partlabel }, rpios_bootfs) {
  const mountpoint = await getMountPoint(partlabel)
  await $`wipefs -a ${path}`
  await $`mkfs.vfat -F32 ${path} -n ${partlabel}`
  await $`mount ${path} ${mountpoint}`

  // We don't clone the block device because the source partition is smaller than the target partition
  // it also means we don't have to resize the target partition (treacherous with vfat)
  // or inherit from the RPI OS bootfs uuid/label
  await $`cp -a ${rpios_bootfs.mountpoint}/. ${mountpoint}/`
  // alternatively but not useful for vfat
  // await $`rsync -a ${rpios_bootfs.mountpoint}/ ${mountpoint}/`
}

async function create_rootfs({ path, partlabel }, rpios_rootfs) {
  const mountpoint = await getMountPoint(partlabel)
  await $`wipefs -a ${path}`
  await $`mkfs.ext4 -q -L ${partlabel} ${path}`
  await $`mount ${path} ${mountpoint}`

  // We don't clone the block device because rsync is faster than dd, e2image or partclone
  // it also means we don't have to resize the target partition
  // or inherit from the RPI OS rootfs uuid/label
  await $`rsync -axHAXES --filter=${"-x security.selinux"} ${rpios_rootfs.mountpoint}/ ${mountpoint}/`

  await mkdir(join(mountpoint, "bootloader"))
  await mkdir(join(mountpoint, "data"))

  await backupAndRemove(
    join(
      mountpoint,
      "/etc/systemd/system/sysinit.target.wants/rpi-resize.service",
    ),
  )
  // await backupAndRemove(
  //   join(
  //     mountpoint,
  //     "/etc/systemd/system/sysinit.target.wants/regenerate_ssh_host_keys.service",
  //   ),
  // )
}

async function create_datafs({ path, partlabel }) {
  const mountpoint = await getMountPoint(partlabel)
  await $`wipefs -a ${path}`
  await $`mkfs.ext4 -q -L ${partlabel} ${path}`
  await $`mount ${path} ${mountpoint}`

  // FIXME: For some reason cloud-init does not or cannot create /home/pi
  // without this - and we are greeted with
  // Could not chdir to home directory /home/pi: No such file or directory
  const homedir = join(mountpoint, "/home/pi")
  await mkdir(homedir, { recursive: true })
  await chown(homedir, 1000, 1000)
  await chmod(homedir, 0o755)
}

// TODO: Investigate if we can replace cloud init with a simpler systemd solution
async function setup_cloudinit(rpios_partitions, partitions) {
  // By default RPI OS reads cloud init config from /boot/firmware
  // since we don't mount /boot/firmware; we move the cloud-init config to /bootloader

  const bootfs = rpios_partitions["bootfs"].mountpoint
  const rootfs = rpios_partitions["rootfs"].mountpoint
  const bootloader = partitions["BOOTLOADER"].mountpoint

  // meta-data
  await copyFile(join(bootfs, "meta-data"), join(bootloader, "meta-data"))
  for (const bootname of ["A", "B"]) {
    const mp = partitions[`FIRMWARE ${bootname}`].mountpoint
    await backupAndRemove(join(mp, "meta-data"))
  }

  // network-config
  await copyFile(
    join(bootfs, "network-config"),
    join(bootloader, "network-config"),
  )
  for (const bootname of ["A", "B"]) {
    const mp = partitions[`FIRMWARE ${bootname}`].mountpoint
    await backupAndRemove(join(mp, "network-config"))
  }

  // user-data
  await copyFile(
    fileURLToPath(import.meta.resolve("./user-data.yaml")),
    join(bootloader, "user-data"),
  )
  for (const bootname of ["A", "B"]) {
    const mp = partitions[`FIRMWARE ${bootname}`].mountpoint
    await backupAndRemove(join(mp, "user-data"))
  }

  // update cloud-init source
  const path_cfg = "/etc/cloud/cloud.cfg.d/99_raspberry-pi.cfg"
  let cfg = await readFile(join(rootfs, path_cfg), "utf8")
  cfg = cfg.replace(
    "seedfrom: file:///boot/firmware",
    "seedfrom: file:///bootloader",
  )
  for (const bootname of ["A", "B"]) {
    const mp = partitions[`ROOT ${bootname}`].mountpoint
    await backupAndReplace(join(mp, path_cfg), cfg)
  }
}

async function setup_config(rpios_partitions, partitions) {
  const content = await readFile(
    join(rpios_partitions["bootfs"].mountpoint, "config.txt"),
    "utf8",
  )

  const config =
    dedent`
    [boot_partition=2]
    cmdline=cmdline-A.txt
    [boot_partition=3]
    cmdline=cmdline-B.txt

    ` + content

  for (const bootname of ["A", "B"]) {
    const part = partitions[`FIRMWARE ${bootname}`]
    const path = join(part.mountpoint, "config.txt")
    await backupAndReplace(path, config)
  }
}

async function setup_cmdline(rpios_partitions, partitions) {
  const rpios_bootfs = rpios_partitions["bootfs"]
  const rpios_rootfs = rpios_partitions["rootfs"]
  const content = await readFile(
    join(rpios_bootfs.mountpoint, "cmdline.txt"),
    "utf8",
  )

  const args = content.trim().split(" ")
  // remove resize
  // undocumented, no idea what it does
  // we also remove rpi-resize.service
  const resize_idx = args.findIndex((arg) => arg === "resize")
  assert.notEqual(resize_idx, -1)
  args.splice(resize_idx, 1)

  // root needs to be updated
  const root_idx = args.findIndex(
    (arg) => arg === `root=PARTUUID=${rpios_rootfs.partuuid}`,
  )
  assert.notEqual(resize_idx, -1)

  // since we don't have / in /etc/fstab we need to specify rw
  args.push("rw")

  // generate a cmdline for each bootname
  const cmdlines = []
  for (const bootname of ["A", "B"]) {
    const rootfs = partitions[`ROOT ${bootname}`]
    const clone = structuredClone(args)
    clone[root_idx] = `root=PARTUUID=${rootfs.partuuid}`
    cmdlines.push([`cmdline-${bootname}.txt`, clone.join(" ")])
  }

  // write all cmdline files to all firmware partitions
  // see config.txt
  for (const bootname of ["A", "B"]) {
    const firmware_mp = partitions[`FIRMWARE ${bootname}`].mountpoint
    for (const [file, content] of cmdlines) {
      await writeFile(join(firmware_mp, file), content)
    }
    // remove original cmdline.txt
    await backupAndRemove(join(firmware_mp, "cmdline.txt"))
  }
}

// So the default of RPI OS is
// mount rootfs to /
// mount bootfs to /boot/firmware
// in a A/B partition setup we want the same /etc/fstab on both A and B
// but we don't know which one is rootfs A/B and which one is bootfs A/B
// thankefully we don't need them in /etc/fstab
// cmdline tells the kernel how to mount / (via root)
// /boot/firmware does not need to be mounted in a image based updates filesystem
// only apt upgrade and rpi specific tools would require /boot/firmware
async function setup_fstab(partitions) {
  const bootloader_partuuid = partitions[`BOOTLOADER`].partuuid
  const datafs_partuuid = partitions[`DATA`].partuuid
  const fstab = dedent`
    PARTUUID=${bootloader_partuuid} /bootloader vfat  defaults,ro      0 2
    PARTUUID=${datafs_partuuid} /data           ext4  defaults,noatime 0 2
    /data/home                  /home           none  bind             0 0
    /data/machine-id            /etc/machine-id none  bind 0 0
  `
  // TODO: when we go readonly
  // /data/varlib              /var/lib none  bind             0 0
  // tmpfs                     /tmp     tmpfs defaults,nosuid,nodev,mode=1777 0 0
  // tmpfs                     /var/tmp tmpfs defaults,nosuid,nodev,mode=1777 0 0
  // tmpfs                     /run     tmpfs defaults,nosuid,nodev           0 0
  // tmpfs                     /var/log tmpfs defaults,nosuid,nodev,mode=0755 0 0`

  for (const bootname of ["A", "B"]) {
    const path = join(partitions[`ROOT ${bootname}`].mountpoint, "etc/fstab")
    await backupAndReplace(path, fstab)
  }
}

async function getPartitions(device) {
  const devices = await getBlockDevices(device)
  const partitions = Object.create(null)
  for (const dev of devices) {
    if (!dev.partuuid) continue
    partitions[dev.partlabel] = dev
  }
  assert.equal(Object.keys(partitions).length, 6)
  assert.ok(partitions["BOOTLOADER"])
  assert.ok(partitions["FIRMWARE A"])
  assert.ok(partitions["FIRMWARE B"])
  assert.ok(partitions["ROOT A"])
  assert.ok(partitions["ROOT B"])
  assert.ok(partitions["DATA"])
  return partitions
}

async function setup_autoboot(partitions) {
  const bootloaderfs = partitions["BOOTLOADER"]
  const firmwarefs_a = partitions["FIRMWARE A"]
  const firmwarefs_b = partitions["FIRMWARE B"]

  let content = await readFile(
    fileURLToPath(import.meta.resolve("./autoboot.ini")),
    "utf-8",
  )
  const config = parse(content)
  config.all.boot_partition = firmwarefs_a.partn
  config.tryboot.boot_partition = firmwarefs_b.partn

  await writeFile(
    join(bootloaderfs.mountpoint, "autoboot.txt"),
    stringify(config),
  )
}
