#!/usr/bin/env node

import { readFile, writeFile, rename } from "node:fs/promises"
import assert from "node:assert"
import { $ } from "execa"
import { join } from "path"
import { stringify, parse } from "ini"
import { fileURLToPath } from "url"

const [, , rpios_device, device] = process.argv

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

async function getBlockDevices(device) {
  const { stdout } =
    await $`lsblk --json --output=PATH,PARTUUID,LABEL,MOUNTPOINT,FSTYPE,PARTN ${device}`

  const { blockdevices } = JSON.parse(stdout)

  const devs = Object.create(null)

  for (const dev of blockdevices) {
    if (!dev.partuuid) continue
    devs[dev.label] = dev
  }

  return devs
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

const rpios_partitions = await getRaspberryPiOSPartitions(rpios_device)
const partitions = await getPartitions(device)

await process_fstab(rpios_partitions, partitions, "A")
await process_fstab(rpios_partitions, partitions, "B")
await process_cmdline(rpios_partitions, partitions, "A")
await process_cmdline(rpios_partitions, partitions, "B")
await process_automount(partitions)
