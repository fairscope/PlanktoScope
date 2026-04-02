import assert from "node:assert"
import {
  getBlockDevices,
  backupAndReplace,
  assertReplace,
  lsblk,
} from "./lib.js"
import { $ } from "execa"
import { readFile, writeFile, rename, mkdir } from "node:fs/promises"
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

  await create_autobootfs(partitions["AUTOBOOT"])

  const rpios_bootfs = rpios_partitions["bootfs"]
  await create_bootfs(partitions["BOOTFS A"], rpios_bootfs)
  await create_bootfs(partitions["BOOTFS B"], rpios_bootfs)

  const rpios_rootfs = rpios_partitions["rootfs"]
  await create_rootfs(partitions["ROOTFS A"], rpios_rootfs)
  await create_rootfs(partitions["ROOTFS B"], rpios_rootfs)

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

  // # Partition 1: 8MB FAT12 "AUTOBOOT"
  await $`sgdisk --new=1:0:+32K --typecode=1:0700 -A 1:set:0 -A 1:set:1 -A 1:set:62 -A 1:set:63 --change-name=1:AUTOBOOT ${device}`
  // # Partition 2: 512MB FAT32 "BOOTFS A"
  await $`sgdisk --new=2:0:+256M --typecode=2:0700 -A 2:set:0 -A 2:set:1 -A 2:set:62 -A 2:set:63 --change-name=2:${"BOOTFS A"} ${device}`
  // # Partition 3: 512MB FAT32 "BOOTFS B"
  await $`sgdisk --new=3:0:+256M --typecode=3:0700 -A 3:set:0 -A 3:set:1 -A 3:set:62 -A 3:set:63 --change-name=3:${"BOOTFS B"} ${device}`
  // # Partition 4: 12GB EXT4 "ROOTFS A"
  await $`sgdisk --new=4:0:+10G --typecode=4:8300 -A 4:set:0 -A 4:set:1 -A 4:set:62 -A 4:set:63 --change-name=4:${"ROOTFS A"} ${device}`
  // # Partition 5: 12GB EXT4 "ROOTFS B"
  await $`sgdisk --new=5:0:+10G --typecode=5:8300 -A 5:set:0 -A 5:set:1 -A 5:set:62 -A 5:set:63 --change-name=5:${"ROOTFS B"} ${device}`
  // # Partition 6: Remaining space EXT4 "DATA"
  await $`sgdisk --new=6:0:0 --typecode=6:8300 -A 6:set:0 -A 6:set:1  -A 6:set:62 -A 6:set:63 --change-name=6:DATA ${device}`

  await $`sgdisk --verify ${device}`

  // Inform kernel of partition table changes
  await $`partprobe ${device}`
  // Inform userspace of partition table changes
  await $`udevadm settle`
}

async function create_autobootfs({ partlabel, path }) {
  const { stdout: mountpoint } = await $`mktemp -d`
  await $`wipefs -a ${path}`
  await $`mkfs.vfat -F12 ${path} -n ${partlabel}`
  await $`mount ${path} ${mountpoint}`
  await $`cp autoboot.ini ${join(mountpoint, "autoboot.txt")}`
}

async function create_bootfs({ path, partlabel }, rpios_bootfs) {
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
  await backupAndReplace(`${mountpoint}/user-data`, data)
}

/*
  create_bootfs with rsync
  alternative implementation, left here in case it proves useful in the future
*/
// async function create_bootfs_with_rsync({path, partlabel}, rpios_bootfs) {
//   const { stdout: mountpoint } = await $`mktemp -d`
//   await $`wipefs -a ${path}`
//   await $`mkfs.vfat -F32 ${path} -n ${partlabel}`
//   await $`mount ${path} ${mountpoint}`
//   await $`rsync -a ${rpios_bootfs.mountpoint}/ ${mountpoint}/`
//   await $`mv ${mountpoint}/user-data ${mountpoint}/user-data.orig`
//   await $`cp user-data.yaml ${mountpoint}/user-data`
// }

async function create_rootfs({ path, partlabel }, rpios_rootfs, slot) {
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

async function getPartitions(device) {
  const devices = await getBlockDevices(device)
  const partitions = Object.create(null)
  for (const dev of devices) {
    if (!dev.partuuid) continue
    partitions[dev.partlabel] = dev
    const slot = dev?.label.match(/^[BR]OOTFS ([AB])$/)?.[1]
    if (slot) {
      dev.slot = slot
    }
  }
  assert.equal(Object.keys(partitions).length, 6)
  assert.ok(partitions["AUTOBOOT"])
  assert.ok(partitions["BOOTFS A"])
  assert.ok(partitions["BOOTFS B"])
  assert.ok(partitions["ROOTFS A"])
  assert.ok(partitions["ROOTFS A"])
  assert.ok(partitions["DATA"])
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

async function getRootDevice() {
  const devices = await lsblk(["PKNAME", "PATH", "MOUNTPOINT"])
  const rootpartition = devices.find((device) => device.mountpoint === "/")
  return rootpartition?.pkname ? `/dev/${rootpartition.pkname}` : null
}

async function getStatus() {
  const device = await getRootDevice()
  const partitions = await getPartitions(device)

  const active_partition = Object.values(partitions).find(
    (partition) => partition.mountpoint === "/",
  )

  const active = active_partition.label === "ROOTFS A" ? "A" : "B"
  const inactive = active === "A" ? "B" : "A"
  const autoboot = await readAutoboot(partitions)
  const target = autoboot.all.boot_partition === "2" ? "A" : "B"

  return { device, active, inactive, target, partitions }
}

async function readAutoboot(partitions) {
  const autobootfs = partitions["AUTOBOOT"]

  const is_mounted = !!autobootfs.mountpoint
  if (!is_mounted) {
    const { stdout: mountpoint } = await $`mktemp -d`
    await $`mount ${autobootfs.path} ${mountpoint}`
    autobootfs.mountpoint = mountpoint
  }

  try {
    const content = await readFile(
      join(autobootfs.mountpoint, "autoboot.txt"),
      "utf-8",
    )
    const config = parse(content)
    return config
  } finally {
    if (!is_mounted) {
      await $`umount ${autobootfs.mountpoint}`
    }
  }
}

async function slotToImage() {
  const status = await getStatus()
  const { partitions, active, inactive } = status

  const bootfs = partitions[`BOOTFS ${inactive}`]
  const rootfs = partitions[`ROOTFS ${inactive}`]

  console.time("bootfs")
  const path_bootfs = await partitionToImage(bootfs)
  console.timeEnd("bootfs")

  console.time("rootfs")
  const path_rootfs = await partitionToImage(rootfs)
  console.timeEnd("rootfs")

  console.log(path_bootfs, path_rootfs)

  // const bootfs_image_path = await partitionToImage(bootfs)
  // const rootfs_image_path = await partitionToImage(rootfs)

  // await rename(rootfs_path, "/home/pi/data/wow.partclone.ext4.xz")
}

function partitionFilename(partition) {
  return partition.label + `.partclone.${partition.fstype}.xz`
}

async function partitionToImage(partition, path) {
  path = join(path, partitionFilename(partition))
  // FIXME: even if partclone returns with exit code 1 - this does not throw
  // FIXME: why are quotes needed around ${path}?
  await $({
    shell: true,
  })`partclone.${partition.fstype} --quiet --clone --source ${partition.path} -o - | xz --compress --stdout -T0 > "${path}"`
  return path
}

async function imageToPartition(path, partition) {
  path = join(path, partitionFilename(partition))
  // FIXME: even if partclone returns with exit code 1 - this does not throw
  // FIXME: why are quotes needed around ${path}?
  await $({
    shell: true,
  })`xz --decompress --stdout "${path}" | partclone.${partition.fstype} --restore --output ${partition.path}`
}

async function backupInactiveSlot() {
  const status = await getStatus()
  const { partitions, inactive } = status

  const bootfs = partitions[`BOOTFS ${inactive}`]
  const rootfs = partitions[`ROOTFS ${inactive}`]

  const dir = `/home/pi/data/internals/partitions\ ${new Date().toISOString()}`
  await mkdir(dir, { recursive: true })

  const path_bootfs = await partitionToImage(bootfs, dir)
  const path_rootfs = await partitionToImage(rootfs, dir)

  return dir
}

async function restoreInactiveSlot(dir) {
  const status = await getStatus()
  const { partitions, inactive } = status

  const bootfs = partitions[`BOOTFS ${inactive}`]
  const rootfs = partitions[`ROOTFS ${inactive}`]

  await imageToPartition(dir, bootfs)
  await imageToPartition(dir, rootfs)
}

// const dir = await backupInactiveSlot()
// await restoreInactiveSlot(dir)
