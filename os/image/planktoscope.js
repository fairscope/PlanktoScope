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

  await create_autobootfs(device)

  // 11s not in parallel
  await create_bootfs(device, "A", rpios_partitions)
  await create_bootfs(device, "B", rpios_partitions)

  // 2m55 with dd
  await create_rootfs(device, "A", rpios_partitions)
  await create_rootfs(device, "B", rpios_partitions)
  await create_datafs(device)
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

  // # Partition 1: 8MB FAT12 "AUTOBOOT"
  await $`sgdisk --new=1:0:+8M --typecode=1:0700 -A 1:set:0 -A 1:set:1 -A 1:set:62 -A 1:set:63 --change-name=1:AUTOBOOT ${device}`
  // # Partition 2: 512MB FAT32 "BOOTFS A"
  await $`sgdisk --new=2:0:+512M --typecode=2:0700 -A 2:set:0 -A 2:set:1 -A 2:set:62 -A 2:set:63 --change-name=2:${"BOOTFS A"} ${device}`
  // # Partition 3: 512MB FAT32 "BOOTFS B"
  await $`sgdisk --new=3:0:+512M --typecode=3:0700 -A 3:set:0 -A 3:set:1 -A 3:set:62 -A 3:set:63 --change-name=3:${"BOOTFS B"} ${device}`
  // # Partition 4: 12GB EXT4 "ROOTFS A"
  await $`sgdisk --new=4:0:+12G --typecode=4:8300 -A 4:set:0 -A 4:set:1 -A 4:set:62 -A 4:set:63 --change-name=4:${"ROOTFS A"} ${device}`
  // # Partition 5: 12GB EXT4 "ROOTFS B"
  await $`sgdisk --new=5:0:+12G --typecode=5:8300 -A 5:set:0 -A 5:set:1 -A 5:set:62 -A 5:set:63 --change-name=5:${"ROOTFS B"} ${device}`
  // # Partition 6: Remaining space EXT4 "DATA"
  await $`sgdisk --new=6:0:0 --typecode=6:8300 -A 6:set:0 -A 6:set:1  -A 6:set:62 -A 6:set:63--change-name=6:"DATA" ${device}`

  await $`sgdisk --verify ${device}`

  // Inform kernel of partition table changes
  await $`partprobe ${device}`
}

async function create_autobootfs(device) {
  const label = "AUTOBOOT"
  const path = `${device}1`
  const { stdout: mountpoint } = await $`mktemp -d`
  await $`wipefs -a ${path}`
  await $`mkfs.vfat -F12 ${path} -n ${label}`
  await $`mount ${path} ${mountpoint}`
  await $`cp autoboot.ini ${join(mountpoint, "autoboot.txt")}`
}

async function create_bootfs(device, AB, rpios_partitions) {
  AB = AB.toUpperCase()
  if (!["A", "B"].includes(AB)) throw new Error("Unknown AB")
  const label = `BOOTFS ${AB}`
  const path = device + (AB === "A" ? "2" : "3")
  const { stdout: mountpoint } = await $`mktemp -d`
  await $`wipefs -a ${path}`

  await $`partclone.${rpios_partitions.bootfs.fstype} --dev-to-dev --source ${rpios_partitions.bootfs.path} --overwrite ${path} --quiet`
  // alternative with dd - slower
  // await $`dd if=${rpios_partitions.bootfs.path} of=${path} bs=1M`

  // update the filesystem UUID so it's not the same as RPI OS
  const serial = "0x" + crypto.randomBytes(4).toString("hex").toUpperCase()
  // update the filesystem UUID so it's not the same as RPI OS
  // set filesystem label
  // TODO: investigatee why it displays "Hidden (2560) does not match sectors (63)"
  await $`mlabel -i ${path} -N ${serial} ::${label}`
  // await $`fsck.vfat -n ${path}` // check filesystem
  // await $`fatresize -s max ${path}` // resize to take remaining space
  // await $`fsck.vfat -n ${path}` // check filesystem
  await $`mount ${path} ${mountpoint}`

  const data = await readFile(
    fileURLToPath(import.meta.resolve("./user-data.yaml")),
  )
  await backupAndReplace(`${mountpoint}/user-data`, data)
}

/*
  create_bootfs with rsync
  alternative implementation, left here in case it proves useful in the future
*/
// async function create_bootfs_with_rsync(device, AB, rpios_partitions) {
//   AB = AB.toUpperCase()
//   if (!["A", "B"].includes(AB)) throw new Error("Unknown AB")
//   const label = `BOOTFS ${AB}`
//   const path = device + (AB === "A" ? "2" : "3")
//   const { stdout: mountpoint } = await $`mktemp -d`
//   await $`wipefs -a ${path}`
//   await $`mkfs.vfat -F32 ${path} -n ${label}`
//   await $`mount ${path} ${mountpoint}`
//   await $`rsync -a ${rpios_partitions["bootfs"].mountpoint}/ ${mountpoint}/`
//   await $`mv ${mountpoint}/user-data ${mountpoint}/user-data.orig`
//   await $`cp user-data.yaml ${mountpoint}/user-data`
// }

async function create_rootfs(device, AB, rpios_partitions) {
  AB = AB.toUpperCase()
  if (!["A", "B"].includes(AB)) throw new Error("Unknown AB")
  const label = `ROOTFS ${AB}`
  const path = device + (AB === "A" ? "4" : "5")
  const { stdout: mountpoint } = await $`mktemp -d`
  await $`wipefs -a ${path}`

  await $`partclone.${rpios_partitions.rootfs.fstype} --dev-to-dev --source ${rpios_partitions.rootfs.path} --overwrite ${path} --quiet`
  // alternative with dd - slower
  // await $`dd if=${rpios_partitions.rootfs.path} of=${path} bs=1M`
  // TODO: Look into https://github.com/yoctoproject/bmaptool

  await $`tune2fs -U ${crypto.randomUUID()} ${path}` // update the filesystem UUID so it's not the same as RPI OS
  await $`e2label ${path} ${label}` // set filesystem label
  await $`e2fsck -y -f ${path}` // check filesystem
  await $`resize2fs ${path}` // resize to take remaining space
  await $`mount ${path} ${mountpoint}`
}

/*
  create_rootfs with rsync
  alternative implementation, left here in case it proves useful in the future
  it is actually faster but less exact
*/
// async function create_rootfs_with_rsync(device, AB, rpios_partitions) {
//   AB = AB.toUpperCase()
//   if (!["A", "B"].includes(AB)) throw new Error("Unknown AB")
//   const label = `ROOTFS ${AB}`
//   const path = device + (AB === "A" ? "4" : "5")
//   const { stdout: mountpoint } = await $`mktemp -d`
//   await $`wipefs -a ${path}`
//   await $`mkfs.ext4 -q -L ${label} ${path}`
//   await $`mount ${path} ${mountpoint}`
//   await $`rsync -axHAXES --filter=${"-x security.selinux"} ${rpios_partitions["rootfs"].mountpoint}/ ${mountpoint}/`
// }

async function create_datafs(device) {
  const label = `DATA`
  const path = `${device}6`
  const { stdout: mountpoint } = await $`mktemp -d`
  await $`wipefs -a ${path}`
  await $`mkfs.ext4 -q -L ${label} ${path}`
  await $`mount ${path} ${mountpoint}`
}

async function process_cmdline(rpios_partitions, partitions, AB) {
  const rootfs = partitions[`ROOTFS ${AB.toUpperCase()}`]
  const bootfs = partitions[`BOOTFS ${AB.toUpperCase()}`]
  const path = join(bootfs.mountpoint, "cmdline.txt")

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

async function process_fstab(rpios_partitions, partitions, AB) {
  const bootfs = partitions[`BOOTFS ${AB.toUpperCase()}`]
  const rootfs = partitions[`ROOTFS ${AB.toUpperCase()}`]
  const datafs = partitions[`DATA`]
  const path = join(rootfs.mountpoint, "etc/fstab")

  const rpios_bootfs_partuuid = rpios_partitions["bootfs"].partuuid
  const rpios_rootfs_partuuid = rpios_partitions["rootfs"].partuuid

  let content = await readFile(path, "utf-8")

  content = content.trim()
  content = assertReplace(
    content,
    `PARTUUID=${rpios_bootfs_partuuid} `,
    `PARTUUID=${bootfs.partuuid} `,
  )
  content = assertReplace(
    content,
    `PARTUUID=${rpios_rootfs_partuuid} `,
    `PARTUUID=${rootfs.partuuid} `,
  )
  content += `\nPARTUUID=${datafs.partuuid} /home/pi/data ${datafs.fstype} defaults,noatime 0 2`

  await backupAndReplace(path, content)
}

// device should be a disk device such as /dev/sdb
async function getPartitions(device) {
  const partitions = await getBlockDevices(device)
  assert.equal(Object.keys(partitions).length, 6)
  return partitions
}

async function process_autoboot(partitions) {
  const autobootfs = partitions["AUTOBOOT"]
  const bootfs_a = partitions["BOOTFS A"]
  // const bootfs_b = partitions["BOOTFS B"]

  let content = await readFile(
    fileURLToPath(import.meta.resolve("./autoboot.ini")),
    "utf-8",
  )
  const config = parse(content)
  config.all.boot_partition = bootfs_a.partn

  await writeFile(
    join(autobootfs.mountpoint, "autoboot.txt"),
    stringify(config),
  )
}
