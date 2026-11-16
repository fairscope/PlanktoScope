#!/usr/bin/env node

import { $ } from "../../lib/exec.js"
import { umount } from "./lib.js"
import { chown } from "node:fs/promises"

if (import.meta.main) {
  if (process.getuid() !== 0) {
    throw new Error("Please run as sudo.")
  }

  const device = process.argv[2]
  assert.ok(device)
  const path = process.argv[3]
  assert.ok(path)
  await createImage(device, path)
}

export async function createImage(device, path) {
  await umount(device)

  await $`dd bs=4M if=${device} conv=sparse,fsync of=${path}`
  await chownToRealUser(path)

  const { stdout: loop_device } =
    await $`losetup --find --show --partscan ${path}`

  try {
    // BOOTLOADER
    await $`fsck.vfat -n ${loop_device}p1`
    // FIRMWARE_A
    await $`fsck.vfat -n ${loop_device}p2`
    // FIRMWARE_B
    await $`fsck.vfat -n ${loop_device}p3`
    // ROOT_A
    await $`fsck.ext4 -fn ${loop_device}p4`
    await $`zerofree ${loop_device}p4`
    // ROOT_B
    await $`fsck.ext4 -fn ${loop_device}p5`
    await $`zerofree ${loop_device}p5`
    // DATA
    await $`fsck.ext4 -fn ${loop_device}p6`
    await $`zerofree ${loop_device}p6`
  } finally {
    await $`losetup -d ${loop_device}`
  }

  await $`fallocate --dig-holes ${path}`

  await $`bmaptool create ${path} --output ${path}.bmap`
  await chownToRealUser(`${path}.bmap`)
  await $`xz -T0 -9e --keep -v ${path}`
  await chownToRealUser(`${path}.xz`)
}

async function chownToRealUser(path) {
  const uid = Number(process.env.SUDO_UID)
  const gid = Number(process.env.SUDO_GID)
  if (!uid || !gid) return // not run through sudo (e.g. real root login)
  await chown(path, uid, gid)
}
