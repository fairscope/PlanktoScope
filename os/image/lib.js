import { mkdir } from "node:fs/promises"
import { fileURLToPath } from "node:url"
import { join } from "path"

import { $ } from "../../lib/exec.js"

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

const builddir = fileURLToPath(import.meta.resolve("./.build"))
export async function getMountPoint(name) {
  const mp = join(builddir, name.replace(" ", "_"))
  await mkdir(mp, { recursive: true })
  return mp
}

let _booted_device
export async function getBootedDevice() {
  if (!_booted_device) {
    const { stdout: source } = await $`findmnt -no SOURCE /`
    const { stdout: pkname } = await $`lsblk -no PKNAME ${source.trim()}`
    _booted_device = `/dev/${pkname}`
  }
  return _booted_device
}
