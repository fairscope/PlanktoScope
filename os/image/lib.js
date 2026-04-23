#!/usr/bin/env node

import { $ } from "execa"
import { writeFile, rename } from "node:fs/promises"

export async function getBlockDevices(device) {
  const { stdout } =
    await $`lsblk --json --output=PATH,PARTUUID,LABEL,PARTLABEL,MOUNTPOINT,FSTYPE,PARTN ${device}`
  const { blockdevices } = JSON.parse(stdout)
  return blockdevices
}

export async function umount(device) {
  const { stdout } = await $`lsblk --json --output=PATH,MOUNTPOINT ${device}`

  const { blockdevices } = JSON.parse(stdout)

  await Promise.all(
    blockdevices.map((device) =>
      device.mountpoint ? $`umount ${device.mountpoint}` : null,
    ),
  )
}

export async function backupAndReplace(path, data) {
  const backup = path + ".orig"
  const temporary = path + ".tmp"

  await writeFile(temporary, data)
  await rename(path, backup)
  await rename(temporary, path)
}

export function assertReplace(str, a, b) {
  const new_str = str.replace(a, b)
  if (new_str === str) throw new Error("String was not replaced")
  return new_str
}
