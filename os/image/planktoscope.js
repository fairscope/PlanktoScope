import assert from "node:assert"
import { getBlockDevices, backupAndReplace, assertReplace } from "./lib.js"
import { $ } from "execa"
import { readFile, writeFile } from "node:fs/promises"
import { join } from "path"
import { stringify, parse } from "ini"
import { fileURLToPath } from "url"
import crypto from "crypto"

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

  await process_fstab(rpios_partitions, partitions, "A")
  await process_fstab(rpios_partitions, partitions, "B")
  await process_cmdline(rpios_partitions, partitions, "A")
  await process_cmdline(rpios_partitions, partitions, "B")
  await process_autoboot(partitions)
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
  // # Partition 2: 512MB FAT32 "FIRMWARE A"
  await $`sgdisk --new=2:0:+512M --typecode=2:0700 -A 2:set:0 -A 2:set:1 -A 2:set:62 -A 2:set:63 --change-name=2:${"FIRMWARE A"} ${device}`
  // # Partition 3: 512MB FAT32 "FIRMWARE B"
  await $`sgdisk --new=3:0:+512M --typecode=3:0700 -A 3:set:0 -A 3:set:1 -A 3:set:62 -A 3:set:63 --change-name=3:${"FIRMWARE B"} ${device}`
  // # Partition 4: 12GB EXT4 "ROOT A"
  await $`sgdisk --new=4:0:+12G --typecode=4:8300 -A 4:set:0 -A 4:set:1 -A 4:set:62 -A 4:set:63 --change-name=4:${"ROOT A"} ${device}`
  // # Partition 5: 12GB EXT4 "ROOT B"
  await $`sgdisk --new=5:0:+12G --typecode=5:8300 -A 5:set:0 -A 5:set:1 -A 5:set:62 -A 5:set:63 --change-name=5:${"ROOT B"} ${device}`
  // # Partition 6: Remaining space EXT4 "DATA"
  await $`sgdisk --new=6:0:0 --typecode=6:8300 -A 6:set:0 -A 6:set:1  -A 6:set:62 -A 6:set:63 --change-name=6:DATA ${device}`

  await $`sgdisk --verify ${device}`

  // Inform kernel of partition table changes
  await $`partprobe ${device}`
  // Inform userspace of partition table changes
  await $`udevadm settle`
}

async function create_bootloaderfs({ partlabel, path }) {
  const { stdout: mountpoint } = await $`mktemp -d`
  await $`wipefs -a ${path}`
  await $`mkfs.vfat -F12 ${path} -n ${partlabel}`
  await $`mount ${path} ${mountpoint}`
  await $`cp autoboot.ini ${join(mountpoint, "autoboot.txt")}`
}

async function create_firmwarefs({ path, partlabel }, rpios_bootfs) {
  const { stdout: mountpoint } = await $`mktemp -d`
  await $`wipefs -a ${path}`

  await $`partclone.${rpios_bootfs.fstype} --dev-to-dev --source ${rpios_bootfs.path} --overwrite ${path} --quiet`
  // alternative with dd - slower
  // await $`dd if=${rpios_partitions.bootfs.path} of=${path} bs=1M`

  // update the filesystem UUID so it's not the same as RPI OS
  const serial = crypto.randomBytes(4).toString("hex").toUpperCase()
  await $`fatlabel -i ${path} ${serial}`

  // set filesystem label
  await $`fatlabel ${path} ${partlabel}`

  await $`fsck.vfat -n ${path}` // check filesystem
  // TODO: figure this out
  // await $`fatresize -s max ${path}` // resize to take remaining space
  // await $`fsck.vfat -n ${path}` // check filesystem
  await $`mount ${path} ${mountpoint}`

  const data = await readFile(
    fileURLToPath(import.meta.resolve("./user-data.yaml")),
  )
  // FIXME: does not work
  // /boot/firmware/userconf and /boot/formware/ssh does
  await backupAndReplace(`${mountpoint}/user-data`, data)
}

/*
  create_firmwarefs with rsync
  alternative implementation, left here in case it proves useful in the future
*/
// async function create_firmwarefs_with_rsync({path, partlabel}, rpios_bootfs) {
//   const { stdout: mountpoint } = await $`mktemp -d`
//   await $`wipefs -a ${path}`
//   await $`mkfs.vfat -F32 ${path} -n ${partlabel}`
//   await $`mount ${path} ${mountpoint}`
//   await $`rsync -a ${rpios_bootfs.mountpoint}/ ${mountpoint}/`
//   await $`mv ${mountpoint}/user-data ${mountpoint}/user-data.orig`
//   await $`cp user-data.yaml ${mountpoint}/user-data`
// }

async function create_rootfs({ path, partlabel }, rpios_rootfs) {
  const { stdout: mountpoint } = await $`mktemp -d`
  await $`wipefs -a ${path}`

  await $`partclone.${rpios_rootfs.fstype} --dev-to-dev --source ${rpios_rootfs.path} --overwrite ${path} --quiet`
  // alternative with dd - slower
  // await $`dd if=${rpios_rootfs.path} of=${path} bs=1M`

  // update the filesystem UUID so it's not the same as RPI OS
  await $`tune2fs -U ${crypto.randomUUID()} ${path}`

  // set filesystem label
  await $`e2label ${path} ${partlabel}`

  await $`e2fsck -y -f ${path}` // check filesystem - required by resize2fs
  await $`resize2fs ${path}` // resize to take remaining space
  await $`mount ${path} ${mountpoint}`
}

/*
  create_rootfs with rsync
  alternative implementation, left here in case it proves useful in the future
  it is actually faster but less exact
*/
// async function create_rootfs_with_rsync({path, partlabel}, rpios_rootfs) {
//   const { stdout: mountpoint } = await $`mktemp -d`
//   await $`wipefs -a ${path}`
//   await $`mkfs.ext4 -q -L ${partlabel} ${path}`
//   await $`mount ${path} ${mountpoint}`
//   await $`rsync -axHAXES --filter=${"-x security.selinux"} ${rpios_rootfs.mountpoint}/ ${mountpoint}/`
// }

async function create_datafs({ path, partlabel }) {
  const { stdout: mountpoint } = await $`mktemp -d`
  await $`wipefs -a ${path}`
  await $`mkfs.ext4 -q -L ${partlabel} ${path}`
  await $`mount ${path} ${mountpoint}`
}

async function process_cmdline(rpios_partitions, partitions, slot) {
  const firmwarefs = partitions[`FIRMWARE ${slot}`]
  const rootfs = partitions[`ROOT ${slot}`]
  const path = join(firmwarefs.mountpoint, "cmdline.txt")

  const rpios_rootfs_partuuid = rpios_partitions["rootfs"].partuuid

  const content = await readFile(path, "utf-8")
  const args = content.trim().split(" ")

  // remove resize
  const resize_idx = args.findIndex((arg) => arg === "resize")
  assert.notEqual(resize_idx, -1)
  args.splice(resize_idx, 1)

  // update root
  const root_idx = args.findIndex(
    (arg) => arg === `root=PARTUUID=${rpios_rootfs_partuuid}`,
  )
  assert.notEqual(resize_idx, -1)
  args[root_idx] = `root=PARTUUID=${rootfs.partuuid}`

  await backupAndReplace(path, args.join(" "))
}

async function process_fstab(rpios_partitions, partitions, slot) {
  const bootloaderfs = partitions["BOOTLOADER"]
  const firmwarefs = partitions[`FIRMWARE ${slot}`]
  const rootfs = partitions[`ROOT ${slot}`]
  const datafs = partitions[`DATA`]
  const path = join(rootfs.mountpoint, "etc/fstab")

  const rpios_bootfs_partuuid = rpios_partitions["bootfs"].partuuid
  const rpios_rootfs_partuuid = rpios_partitions["rootfs"].partuuid

  let content = await readFile(path, "utf-8")

  content = content.trim()
  content = assertReplace(
    content,
    `PARTUUID=${rpios_bootfs_partuuid} `,
    `PARTUUID=${firmwarefs.partuuid} `,
  )
  content = assertReplace(
    content,
    `PARTUUID=${rpios_rootfs_partuuid} `,
    `PARTUUID=${rootfs.partuuid} `,
  )
  content += `\nPARTUUID=${datafs.partuuid} /home/pi/data ${datafs.fstype} defaults,noatime 0 2`
  content += `\nPARTUUID=${bootloaderfs.partuuid} /boot/bootloader ${bootloaderfs.fstype} defaults 0 2`
  content += "\n"

  await backupAndReplace(path, content)
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

async function process_autoboot(partitions) {
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
