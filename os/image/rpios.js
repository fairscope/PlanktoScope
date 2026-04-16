// This file contains code related/specific to Raspberry Pi OS images
// https://www.raspberrypi.com/software/operating-systems/#raspberry-pi-os-64-bit

import assert from "node:assert"
import { basename, join } from "node:path"
import { fileURLToPath } from "node:url"
import { access, readFile, readlink } from "node:fs/promises"

import { $ } from "execa"

import { getBlockDevices, umount } from "./lib.js"
import { getRaspberryPiOSReference } from "./rpi.js"

// ⚠️ IMPORTANT sync reference with setup.sh
const url = `https://downloads.raspberrypi.com/raspios_lite_arm64/images/raspios_lite_arm64-2025-12-04/2025-12-04-raspios-trixie-arm64-lite.img.xz`
const sha256 =
  "681a775e20b53a9e4c7341d748a5a8cdc822039d8c67c1fd6ca35927abbe6290"
const file = basename(url)
const img = basename(url, ".xz")
const reference = file.match(/(.*)-raspios-.*.img/)?.[1]
assert.ok(reference)

async function downloadRaspberryPiOS() {
  // download raspios
  await $`wget -c -nc ${url}`
  // download signature
  await $`wget -c -nc ${url}.sha256`
  // make sure signature hasn't changed
  await $`head -c 64 ${file}.sha256`.pipe`grep -qx ${sha256}`
  // verify signature
  await $`sha256sum --check ${file}.sha256`

  // decompress
  try {
    await access(img)
  } catch {
    await $`unxz --keep ${file}`
  }

  return fileURLToPath(import.meta.resolve(`./${img}`))
}

export async function setupRaspberryPiOSDevice() {
  const path = await downloadRaspberryPiOS()

  const { stdout: device } = await $`losetup --find --partscan --show ${path}`
  await $`partprobe ${device}`
  await $`udevadm settle`

  const partitions = await getRaspberryPiOSPartitions(device)

  return [device, partitions]
}

export async function teardownRaspberryPiOSDevice(device) {
  await umount(device)
  await $`losetup --detach ${device}`
}

export async function mountRaspberryPiOSPartitions(device, partitions) {
  // bootfs
  const { stdout: mpbootfs } = await $`mktemp -d`
  await $`mount ${partitions.bootfs.path} ${mpbootfs}`

  // rootfs
  const { stdout: mprootfs } = await $`mktemp -d`
  await $`mount ${partitions.rootfs.path} ${mprootfs}`

  // verify RPI OS date
  assert.equal(await getRaspberryPiOSReference(mprootfs), reference)

  // TODO: Move this to post-image build tests

  // machine-id
  // https://www.freedesktop.org/software/systemd/man/latest/machine-id.html
  // assert that etc machine-id is uninitialized
  assert.equal(
    await readFile(join(mprootfs, "/etc/machine-id"), "utf8"),
    "uninitialized\n",
  )
  // dbus machine-id does not exist yet, some component will create a link
  assert.rejects(readlink(join(mprootfs, "/var/lib/dbus/machine-id")), {
    code: "ENOENT",
  })

  return getRaspberryPiOSPartitions(device)
}

async function getRaspberryPiOSPartitions(device) {
  const devices = await getBlockDevices(device)
  const partitions = Object.create(null)
  for (const dev of devices) {
    if (!dev.partuuid) continue
    partitions[dev.label] = dev
  }
  assert.equal(Object.keys(partitions).length, 2)
  assert.ok(partitions.bootfs)
  assert.ok(partitions.rootfs)
  return partitions
}

if (import.meta.main) {
  let rpios_device, rpios_partitions
  try {
    ;[rpios_device, rpios_partitions] = await setupRaspberryPiOSDevice()
    // eslint-disable-next-line no-unused-vars
    rpios_partitions = await mountRaspberryPiOSPartitions(
      rpios_device,
      rpios_partitions,
    )
  } finally {
    rpios_device && (await teardownRaspberryPiOSDevice(rpios_device))
  }
}
