// This file contains code related/specific to Raspberry Pi OS images
// https://www.raspberrypi.com/software/operating-systems/#raspberry-pi-os-64-bit

import assert from "node:assert"
import { basename, join } from "node:path"
import { access, readFile, readlink } from "node:fs/promises"
import { once } from "node:events"

import { $ } from "../../lib/exec.js"

import { getBlockDevices, umount, getMountPoint } from "./lib.js"
import { getRaspberryPiOSReference } from "./rpi.js"

// ⚠️ IMPORTANT sync reference with setup.sh
const url = `https://downloads.raspberrypi.com/raspios_lite_arm64/images/raspios_lite_arm64-2026-06-19/2026-06-18-raspios-trixie-arm64-lite.img.xz`
const sha256 =
  "acff736ca7945e3b305f07cda4abdb870910e12634991da69783611756e381b3"
const file = basename(url)
const img = basename(url, ".xz")
const reference = file.match(/(.*)-raspios-.*.img/)?.[1]
assert.ok(reference)

async function downloadRaspberryPiOS() {
  const cwd = process.cwd()

  process.chdir("/data/tmp")

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

  process.chdir(cwd)

  return join("/data/tmp", img)
}

export async function setupRaspberryPiOSDevice() {
  const path = await downloadRaspberryPiOS()

  const { stdout: device } = await $`losetup --find --partscan --show ${path}`
  await $`partprobe ${device}`
  await $`udevadm settle`

  let partitions = await getRaspberryPiOSPartitions(device)
  await mountRaspberryPiOSPartitions(device, partitions)
  partitions = await getRaspberryPiOSPartitions(device)

  return [device, partitions]
}

export async function teardownRaspberryPiOSDevice(device) {
  await umount(device)
  await $`losetup --detach ${device}`
}

async function mountRaspberryPiOSPartitions(device, partitions) {
  // bootfs
  const mpbootfs = await getMountPoint("RPIOS bootfs")
  await $`mount -o ro ${partitions.bootfs.path} ${mpbootfs}`

  // rootfs
  const mprootfs = await getMountPoint("RPIOS rootfs")
  await $`mount -o ro ${partitions.rootfs.path} ${mprootfs}`

  // verify RPI OS date
  assert.equal(await getRaspberryPiOSReference(mprootfs), reference)
  // TODO: there is also mpbootfs/issue.txt

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
  // Keep process running
  let interval = setInterval(() => {}, 1 << 30)

  const [rpios_device, rpios_partitions] = await setupRaspberryPiOSDevice()
  Object.entries(rpios_partitions).forEach(([label, part]) => {
    console.log(`Raspberry Pi OS ${label} mounted to ${part.mountpoint}`)
  })
  console.log("Exit to unmount")

  await Promise.race([once(process, "SIGINT"), once(process, "SIGTERM")])
  clearInterval(interval)

  rpios_device && (await teardownRaspberryPiOSDevice(rpios_device))
}
