#!/usr/bin/env node

import { $ } from "execa"

export async function getBlockDevices(device) {
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

export async function umount(device) {
  const { stdout } = await $`lsblk --json --output=PATH,MOUNTPOINT ${device}`

  const { blockdevices } = JSON.parse(stdout)

  await Promise.all(
    blockdevices.map((device) =>
      device.mountpoint ? $`umount ${device.mountpoint}` : null,
    ),
  )
}
