import assert from "node:assert"
import {
  readFile,
  writeFile,
  mkdir,
  copyFile,
  unlink,
  rm,
  chown,
  cp,
} from "node:fs/promises"
import { join } from "node:path"
import { fileURLToPath } from "node:url"
import { v5 as uuidv5 } from "uuid"

import { $ } from "../../lib/exec.js"
import { stringify, parse } from "ini"
import dedent from "dedent"

import { getBlockDevices, getMountPoint } from "./lib.js"

const default_bootnames = ["A", "B"]
const bootnames = default_bootnames

// Fixed namespace UUID
const NAMESPACE = "11311d13-358c-4d63-8e9a-fd2ca83e08ea"
function stablePartUuid(name) {
  return uuidv5(name, NAMESPACE)
}

export async function createPartitions(device, rpios_partitions) {
  // We create the entire partition table first
  // so that a fs can be resized to fill remaining space
  // until next partition - for example with resize2fs
  await createPartitionTable(device)

  const partitions = await getPartitions(device)

  await create_bootloaderfs(partitions["BOOTLOADER"])

  const rpios_bootfs = rpios_partitions["bootfs"]
  for (const bootname of bootnames) {
    await create_firmwarefs(partitions[`FIRMWARE_${bootname}`], rpios_bootfs)
  }

  const rpios_rootfs = rpios_partitions["rootfs"]
  for (const bootname of bootnames) {
    await create_rootfs(partitions[`ROOT_${bootname}`], rpios_rootfs)
  }

  await create_datafs(device, rpios_rootfs)
}

export async function updateMountpoints(device, rpios_partitions) {
  const partitions = await getPartitions(device)

  await setup_cmdline(rpios_partitions, partitions)
  await setup_config(rpios_partitions, partitions)
  await setup_cloudinit(rpios_partitions, partitions)
  await setup_fstab(partitions)
  await setup_autoboot(partitions)
  await setup_machineid(partitions)
  await setup_repart(partitions)
}

async function createPartitionTable(device) {
  // Removes existing GPT/MBR data.
  await $`sgdisk --zap-all ${device}`

  // Create a new partition table
  await $`sgdisk --new ${device}`

  // -A explanation
  // 0 is "Platform required"
  // 1 is "EFI firmware should ignore the content"
  // 62 is "Hidden"
  // 63 is "No drive letter (i.e. do not automount) "
  // See https://en.wikipedia.org/wiki/GUID_Partition_Table#Partition_entries_(LBA_2%E2%80%9333)

  let partn = 0

  // BOOTLOADER
  partn++
  await $`sgdisk --new=${partn}:0:+8M --typecode=${partn}:0700 --change-name=${partn}:BOOTLOADER --partition-guid=${partn}:${stablePartUuid("BOOTLOADER")} ${device}`

  // FIRMWARE X
  for (const bootname of bootnames) {
    partn++
    await $`sgdisk --new=${partn}:0:+256M --typecode=${partn}:0700 --change-name=${partn}:${"FIRMWARE_" + bootname} --partition-guid=${partn}:${stablePartUuid("FIRMWARE_" + bootname)} ${device}`
  }

  // ROOT X
  for (const bootname of bootnames) {
    partn++
    await $`sgdisk --new=${partn}:0:+10G --typecode=${partn}:8300 --change-name=${partn}:${"ROOT_" + bootname} --partition-guid=${partn}:${stablePartUuid("ROOT_" + bootname)} ${device}`
  }

  // "DATA"
  partn++
  await $`sgdisk --new=${partn}:0:0 --typecode=${partn}:8300 --change-name=${partn}:DATA --partition-guid=${partn}:${stablePartUuid("DATA")} ${device}`

  await $`sgdisk --verify ${device}`

  // Inform kernel of partition table changes
  await $`partprobe ${device}`
  // Inform userspace of partition table changes
  await $`udevadm settle`
}

export async function create_bootloaderfs({ partlabel, path }) {
  const mountpoint = await getMountPoint(partlabel)
  await $`wipefs -a ${path}`
  await $`mkfs.vfat -F12 ${path}`
  await $`mount ${path} ${mountpoint}`
  await $`cp autoboot.ini ${join(mountpoint, "autoboot.txt")}`
}

export async function create_firmwarefs({ path, partlabel }, rpios_bootfs) {
  const mountpoint = await getMountPoint(partlabel)
  await $`wipefs -a ${path}`
  await $`mkfs.vfat -F32 ${path}`
  await $`mount ${path} ${mountpoint}`

  // We don't clone the block device because the source partition is smaller than the target partition
  // it also means we don't have to resize the target partition (treacherous with vfat)
  // or inherit from the RPI OS bootfs uuid/label
  await $`cp -a ${rpios_bootfs.mountpoint}/. ${mountpoint}/`
  // alternatively but not useful for vfat
  // await $`rsync -a ${rpios_bootfs.mountpoint}/ ${mountpoint}/`
}

export async function create_rootfs({ path, partlabel }, rpios_rootfs) {
  const mountpoint = await getMountPoint(partlabel)
  await $`wipefs -a ${path}`
  await $`mkfs.ext4 -q ${path}`
  await $`mount ${path} ${mountpoint}`

  // We don't clone the block device because rsync is faster than dd, e2image or partclone.
  // It also means we don't have to resize the target partition or inherit from the RPI OS rootfs uuid/label.
  // In regards to "--exclude /home" - /home is copied in `create_datafs`
  await $`rsync -axHAXES --filter=${"-x security.selinux"} --exclude /home ${rpios_rootfs.mountpoint}/ ${mountpoint}/`

  await mkdir(join(mountpoint, "bootloader"))
  await mkdir(join(mountpoint, "data"))

  await unlink(
    join(
      mountpoint,
      "/etc/systemd/system/sysinit.target.wants/rpi-resize.service",
    ),
  )

  // TODO: host keys should be the same on all slots
  // await unlink(
  //   join(
  //     mountpoint,
  //     "/etc/systemd/system/sysinit.target.wants/regenerate_ssh_host_keys.service",
  //   ),
  // )
}

async function create_datafs(device, rootfs) {
  const partitions = await getPartitions(device)
  const { path, partlabel } = partitions["DATA"]
  const mountpoint = await getMountPoint(partlabel)
  await $`wipefs -a ${path}`
  await $`mkfs.ext4 -q ${path}`

  await $`mount ${path} ${mountpoint}`

  // /data/home
  await $`rsync -axHAXES --filter=${"-x security.selinux"} ${join(rootfs.mountpoint, "/home")}/ ${join(mountpoint, "/home")}/`

  // allow group traversal
  // used to serve files from caddy
  await $`chmod g+x ${join(mountpoint, "/home/pi")}`

  // create /data/tmp
  const path_tmp = join(mountpoint, "tmp")
  await mkdir(path_tmp)
  await chown(path_tmp, 1000, 1000)
}

// We need to share /etc/machine-id so we symlink it from `/data/machine-id` on both slots
// machine-id-setup.service will create it if target does not exist
// https://www.freedesktop.org/software/systemd/man/latest/machine-id.html
export async function setup_machineid(partitions, bootnames = default_bootnames) {
  for (const bootname of bootnames) {
    const root = partitions[`ROOT_${bootname}`].mountpoint

    await rm(join(root, "/etc/machine-id"), { force: true })
    await $`ln -s /data/machine-id ${join(root, "/etc/machine-id")}`

    await rm(join(root, "/var/lib/dbus/machine-id"), { force: true })
    await $`ln -s /data/machine-id ${join(root, "/var/lib/dbus/machine-id")}`

    await copyFile(
      fileURLToPath(import.meta.resolve("./machine-id-setup.service")),
      join(root, "/etc/systemd/system/machine-id-setup.service"),
    )

    await $`ln -s ${join(root, "/etc/systemd/system/machine-id-setup.service")} ${join(root, "/etc/systemd/system/sysinit.target.wants/machine-id-setup.service")}`
  }
}

// TODO: Investigate if we can replace cloud init with a simpler systemd solution
export async function setup_cloudinit(
  rpios_partitions,
  partitions,
  bootnames = default_bootnames,
) {
  // By default RPI OS reads cloud init config from /boot/firmware
  // since we don't mount /boot/firmware; we move the cloud-init config to /bootloader

  const bootfs = rpios_partitions["bootfs"].mountpoint
  const rootfs = rpios_partitions["rootfs"].mountpoint
  const bootloader = partitions["BOOTLOADER"].mountpoint

  // meta-data
  await copyFile(join(bootfs, "meta-data"), join(bootloader, "meta-data"))
  for (const bootname of bootnames) {
    const mp = partitions[`FIRMWARE_${bootname}`].mountpoint
    await unlink(join(mp, "meta-data"))
  }

  // network-config
  await copyFile(
    join(bootfs, "network-config"),
    join(bootloader, "network-config"),
  )
  for (const bootname of bootnames) {
    const mp = partitions[`FIRMWARE_${bootname}`].mountpoint
    await unlink(join(mp, "network-config"))
  }

  // user-data
  await copyFile(
    fileURLToPath(import.meta.resolve("./user-data.yaml")),
    join(bootloader, "user-data"),
  )
  for (const bootname of bootnames) {
    const mp = partitions[`FIRMWARE_${bootname}`].mountpoint
    await unlink(join(mp, "user-data"))
  }

  // update cloud-init source
  const path_cfg = "/etc/cloud/cloud.cfg.d/99_raspberry-pi.cfg"
  let cfg = await readFile(join(rootfs, path_cfg), "utf8")
  assert.ok(cfg.includes("seedfrom: file:///boot/firmware"))
  cfg = cfg.replace(
    "seedfrom: file:///boot/firmware",
    "seedfrom: file:///bootloader",
  )
  for (const bootname of bootnames) {
    const mp = partitions[`ROOT_${bootname}`].mountpoint
    await writeFile(join(mp, path_cfg), cfg)
  }

  // make sure cloud-init-local runs after /bootloader is mounted
  for (const bootname of bootnames) {
    const mp = partitions[`ROOT_${bootname}`].mountpoint
    const override_dir = join(
      mp,
      "/etc/systemd/system/cloud-init-local.service.d/",
    )
    await mkdir(override_dir, {
      recursive: true,
    })
    await copyFile(
      new URL("./cloud-init-local-override.ini", import.meta.url),
      join(override_dir, "override.conf"),
    )
  }
}

export async function setup_config(
  rpios_partitions,
  partitions,
  bootnames = default_bootnames,
) {
  const content = await readFile(
    join(rpios_partitions["bootfs"].mountpoint, "config.txt"),
    "utf8",
  )

  // See https://www.raspberrypi.com/documentation/computers/config_txt.html#boot_partition-2
  let config = "[all]\n\n"
  for (const bootname of bootnames) {
    const part = partitions[`FIRMWARE_${bootname}`]
    config += dedent`
      [boot_partition=${part.partn}]
      cmdline=cmdline-${bootname}.txt
    `
    config += "\n"
  }

  config += "\n[all]\n\n" + content

  for (const bootname of bootnames) {
    const part = partitions[`FIRMWARE_${bootname}`]
    const path = join(part.mountpoint, "config.txt")
    await writeFile(path, config)
  }
}

export async function setup_cmdline(
  rpios_partitions,
  partitions,
  bootnames = default_bootnames,
) {
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
  for (const bootname of bootnames) {
    const rootfs = partitions[`ROOT_${bootname}`]
    const clone = structuredClone(args)
    clone[root_idx] = `root=PARTUUID=${rootfs.partuuid}`
    cmdlines.push([`cmdline-${bootname}.txt`, clone.join(" ")])
  }

  // write all cmdline files to all firmware partitions
  // see config.txt
  for (const bootname of bootnames) {
    const firmware_mp = partitions[`FIRMWARE_${bootname}`].mountpoint
    for (const [file, content] of cmdlines) {
      await writeFile(join(firmware_mp, file), content)
    }
    // remove original cmdline.txt
    await unlink(join(firmware_mp, "cmdline.txt"))
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
export async function setup_fstab(partitions, bootnames = default_bootnames) {
  const bootloader_partuuid = partitions[`BOOTLOADER`].partuuid
  const datafs_partuuid = partitions[`DATA`].partuuid
  const fstab = dedent`
    PARTUUID=${bootloader_partuuid} /bootloader      vfat  defaults,noatime,ro  0 2
    PARTUUID=${datafs_partuuid}     /data            ext4  defaults,noatime,x-systemd.growfs  0 2
    /data/home                      /home            none  bind  0 0
  `
  // TODO: when we go readonly
  // /data/varlib              /var/lib none  bind             0 0
  // tmpfs                     /tmp     tmpfs defaults,nosuid,nodev,mode=1777 0 0
  // tmpfs                     /var/tmp tmpfs defaults,nosuid,nodev,mode=1777 0 0
  // tmpfs                     /run     tmpfs defaults,nosuid,nodev           0 0
  // tmpfs                     /var/log tmpfs defaults,nosuid,nodev,mode=0755 0 0`

  for (const bootname of bootnames) {
    const path = join(partitions[`ROOT_${bootname}`].mountpoint, "etc/fstab")
    await writeFile(path, fstab)
  }
}

// repart will resize the DATA GPT partition but won't grow the EXT4 filesystem
// we use x-systemd.growfs in fstab for that
// > Note that these definitions may only be used to create and initialize new partitions or to grow existing ones. In the latter case, it will not grow the contained files systems however; separate mechanisms, such as systemd-growfs(8) may be used to grow the file systems inside of these partitions.
// https://www.freedesktop.org/software/systemd/man/latest/repart.d.html#Description
async function setup_repart(partitions) {
  const datafs_partuuid = partitions[`DATA`].partuuid
  const conf = dedent`
    [Partition]
    UUID=${datafs_partuuid}
    GrowFileSystem=yes
    Type=linux-generic
  `
  for (const bootname of bootnames) {
    const path = join(
      partitions[`ROOT_${bootname}`].mountpoint,
      "usr/lib/repart.d",
    )
    await cp(fileURLToPath(import.meta.resolve("./repart.d")), path, {recursive: true})
    await writeFile(join(path, "60-data.conf"), conf)
  }
}

export async function getPartitions(device) {
  const devices = await getBlockDevices(device)
  const partitions = Object.create(null)
  for (const dev of devices) {
    if (!dev.partuuid) continue
    partitions[dev.partlabel] = dev
  }
  assert.equal(Object.keys(partitions).length, bootnames.length * 2 + 2)
  assert.ok(partitions["BOOTLOADER"])
  for (const bootname of bootnames) {
    assert.ok(partitions[`FIRMWARE_${bootname}`])
    assert.ok(partitions[`ROOT_${bootname}`])
  }
  assert.ok(partitions["DATA"])
  return partitions
}

export async function setup_autoboot(partitions) {
  const bootloaderfs = partitions["BOOTLOADER"]

  const bootname_active = bootnames[0]
  const bootname_fallback = bootnames[1]

  let content = await readFile(
    fileURLToPath(import.meta.resolve("./autoboot.ini")),
    "utf-8",
  )

  const config = parse(content)
  config.all.boot_partition = partitions[`FIRMWARE_${bootname_active}`].partn
  if (bootname_fallback) {
    config.tryboot.boot_partition =
      partitions[`FIRMWARE_${bootname_fallback}`].partn
  }

  await writeFile(
    join(bootloaderfs.mountpoint, "autoboot.txt"),
    stringify(config),
  )
}
