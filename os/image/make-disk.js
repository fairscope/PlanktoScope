#!/usr/bin/env node

// sudo NODE_DEBUG=execa ./make-ab-disk.js /dev/sdb

import assert from "node:assert"
import { umount, getBlockDevices } from "./lib.js"
import { $ } from "execa"
import { readFile, writeFile, rename } from "node:fs/promises"
import { join } from "path"
import { stringify, parse } from "ini"
import { fileURLToPath } from "url"

async function mountRaspiOS(path) {
  // read image file as block device
  const { stdout: rpios_device } =
    await $`losetup --find --partscan --show ${path}`
  assert.ok(rpios_device)

  // mount bootfs
  const { stdout: mpbootfs } = await $`mktemp -d`
  await $`mount ${rpios_device}p1 ${mpbootfs}`

  // mount rootfs
  const { stdout: mprootfs } = await $`mktemp -d`
  await $`mount ${rpios_device}p2 ${mprootfs}`

  return rpios_device
}

async function createPartitions(device, rpios_partitions) {
  // We create the entire partition table first
  // so that a fs can be resized to fill remaining space
  // until next partition - for example with resize2fs
  await createPartitionTable(device)

  await create_autobootfs(device)
  await create_bootfs(device, "A", rpios_partitions)
  await create_bootfs(device, "B", rpios_partitions)
  await create_rootfs(device, "A", rpios_partitions)
  await create_rootfs(device, "B", rpios_partitions)
  await create_datafs(device)
}

async function updateMountpoints(device, rpios_partitions) {
  const partitions = await getPartitions(device)

  await process_fstab(rpios_partitions, partitions, "A")
  await process_fstab(rpios_partitions, partitions, "B")
  await process_cmdline(rpios_partitions, partitions, "A")
  await process_cmdline(rpios_partitions, partitions, "B")
  await process_automount(partitions)
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
  await $`sgdisk --new=1:0:+8M --typecode=1:0700 -A 1:set:0 -A 1:set:1 -A 1:set:62 -A 1:set:63 --change-name=1:"AUTOBOOT" ${device}`
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
  await $`mkfs.vfat -F32 ${path} -n ${label}`
  await $`mount ${path} ${mountpoint}`
  await $`rsync -a ${rpios_partitions["bootfs"].mountpoint}/ ${mountpoint}/`
  await $`mv ${mountpoint}/user-data ${mountpoint}/user-data.orig`
  await $`cp user-data.yaml ${mountpoint}/user-data`
}

async function create_rootfs(device, AB, rpios_partitions) {
  AB = AB.toUpperCase()
  if (!["A", "B"].includes(AB)) throw new Error("Unknown AB")
  const label = `ROOTFS ${AB}`
  const path = device + (AB === "A" ? "4" : "5")
  const { stdout: mountpoint } = await $`mktemp -d`
  await $`wipefs -a ${path}`
  await $`mkfs.ext4 -q -L ${label} ${path}`
  await $`mount ${path} ${mountpoint}`
  await $`rsync -axHAXES --filter=${"-x security.selinux"} ${rpios_partitions["rootfs"].mountpoint}/ ${mountpoint}/`
}

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

  await rename(path, path + ".orig")
  try {
    await writeFile(path, args.join(" "))
  } catch {
    // revert
    await rename(path + ".orig", path)
  }
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

  await rename(path, path + ".orig")
  try {
    await writeFile(path, content)
  } catch {
    // revert
    await rename(path + ".orig", path)
  }
}

function assertReplace(str, a, b) {
  const new_str = str.replace(a, b)
  if (new_str === str) throw new Error("String was not replaced")
  return new_str
}

// device should be a loop device such as /dev/loop1
async function getRaspberryPiOSPartitions(device) {
  const partitions = await getBlockDevices(device)
  assert.equal(Object.keys(partitions).length, 2)
  assert.ok(partitions.bootfs)
  assert.ok(partitions.rootfs)
  return partitions
}

// device should be a disk device such as /dev/sdb
async function getPartitions(device) {
  const partitions = await getBlockDevices(device)
  assert.equal(Object.keys(partitions).length, 6)
  return partitions
}

async function process_automount(partitions) {
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

if (import.meta.main) {
  if (process.getuid() !== 0) {
    throw new Error("Please run as root.")
  }

  const date = "2025-12-04" // sync with setup.sh date
  const img = `${date}-raspios-trixie-arm64-lite.img`
  const file = `${img}.xz`
  const url = `https://downloads.raspberrypi.com/raspios_lite_arm64/images/raspios_lite_arm64-${date}/${file}`
  const sha256 =
    "681a775e20b53a9e4c7341d748a5a8cdc822039d8c67c1fd6ca35927abbe6290"

  // download raspios
  await $`wget -c -nc ${url}`
  // download signature
  await $`wget -c -nc ${url}.sha256`
  // make sure signature hasn't changed
  await $`head -c 64 ${file}.sha256`.pipe`grep -qx ${sha256}`
  // verify signature
  await $`sha256sum --check ${file}.sha256`
  // decompress
  await $`unxz --test --force ${file}`

  const [, , device] = process.argv
  assert.ok(device)

  await umount(device)

  const rpios_device = await mountRaspiOS(
    fileURLToPath(
      import.meta.resolve("./2025-12-04-raspios-trixie-arm64-lite.img"),
    ),
  )
  const rpios_partitions = await getRaspberryPiOSPartitions(rpios_device)

  await createPartitions(device, rpios_partitions)
  await updateMountpoints(device, rpios_partitions)

  await $`sync`
  await umount(device)

  await umount(rpios_device)
  await $`losetup --detach ${rpios_device}`
}
