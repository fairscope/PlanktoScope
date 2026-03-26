import assert from "node:assert"
import { getBlockDevices, umount } from "./lib.js"
import { $ } from "execa"
import { fileURLToPath } from "url"

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

  return getRaspberryPiOSPartitions(device)
}

async function downloadRaspberryPiOS() {
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

  return fileURLToPath(import.meta.resolve(`./${img}`))
}

async function getRaspberryPiOSPartitions(device) {
  const partitions = await getBlockDevices(device)
  assert.equal(Object.keys(partitions).length, 2)
  assert.ok(partitions.bootfs)
  assert.ok(partitions.rootfs)
  return partitions
}
