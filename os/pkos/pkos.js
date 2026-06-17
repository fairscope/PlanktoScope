#!/usr/bin/env node

import { fileURLToPath } from "node:url"
import { join } from "node:path"
import { readFile, writeFile, rm, mkdir } from "node:fs/promises"

import { parse, stringify } from "ini"
import { $ } from "execa"

import {
  getBootPartitionNumber,
  getRaucSlot,
  getBootedSlot,
} from "../rauc/rauc.js"
import { getBootedPartitionNumber } from "../image/rpi.js"
import { getBlockDevices, getBootedDevice } from "../image/lib.js"

const device = await getBootedDevice()

if (import.meta.main) {
  const [, , command, ...args] = process.argv
  if (command === "reboot") {
    const [slot] = args
    if (!slot) {
      throw new Error("reboot A|B")
    }
    await reboot(slot)
  } else if (command === "slot") {
    console.log(await slot())
  } else if (command === "prepare") {
    await prepare()
  } else if (command === "create-bundle") {
    const [device_path, bootname, version] = args
    if (!device_path || !bootname) {
      throw new Error("create-bundle /dev/device A|B [version]")
    }
    const booted_slot = await getBootedSlot()
    if (device_path === device && bootname === booted_slot) {
      throw new Error(
        `Cannot create a bundle for booted ${device} ${bootname} slot.`,
      )
    }
    const bundle_path = await createBundle(device_path, bootname, version)
    console.log(bundle_path)
  } else {
    throw new Error(`Unknwon command "${command}".`)
  }
}

async function reboot(slot) {
  await $`reboot ${await getBootPartitionNumber(slot)}`
}

async function slot() {
  const n = await getBootedPartitionNumber()
  return await getRaucSlot(n)
}

async function prepare() {
  await mount_active_firmware()

  await $({ shell: true, stdio: "inherit" })`/opt/PlanktoScope/os/setup.sh`
  await $({
    shell: true,
    stdio: "inherit",
  })`/opt/PlanktoScope/os/postinstall.sh`
  await $({
    shell: true,
    stdio: "inherit",
  })`sudo /opt/PlanktoScope/os/image/preimage.js`

  console.log(
    `✅ Ready, you can reboot to slot ${(await slot()) === "A" ? "B" : "A"}`,
  )
}

async function createBundle(device, bootname, version) {
  const date = new Date().toISOString()
  const build = date
  version ??= date.split("T")[0]

  const partitions = await getBlockDevices(device)

  const manifest = parse(
    await readFile(
      fileURLToPath(import.meta.resolve("../rauc/manifest.ini")),
      "utf8",
    ),
  )

  const tmpdir = "/data/tmp"
  const bundle_dir = join(tmpdir, "rauc-bundle")
  await rm(bundle_dir, {
    recursive: true,
    force: true,
  })
  await mkdir(bundle_dir, { recursive: true })
  const manifest_path = join(bundle_dir, "manifest.raucm")
  manifest.update.build = build
  manifest.update.version = version
  await writeFile(manifest_path, stringify(manifest))

  const part_firmware = partitions.find(
    (part) => part.partlabel === `FIRMWARE_${bootname}`,
  )
  const part_root = partitions.find(
    (part) => part.partlabel === `ROOT_${bootname}`,
  )

  await $`dd if=${part_firmware.path} of=${join(bundle_dir, manifest.image.FIRMWARE.filename)} bs=64M`

  // TODO: Create a img file instead with "mkfs.ext4 rootfs.img"
  // mount it as loop device "mount -o loop rootfs.img /mnt"
  // then rsync files into it
  await $`dd if=${part_root.path} of=${join(bundle_dir, manifest.image.ROOT.filename)} bs=64M`
  const bundle_path = join(tmpdir, `PlanktoScopeOS-${version}.raucb`)
  await $`rauc --cert ${fileURLToPath(import.meta.resolve("../rauc/planktoscope-rauc-cert.pem"))} --key ${fileURLToPath(import.meta.resolve("../rauc/planktoscope-rauc-key.pem"))} bundle ${bundle_dir} ${bundle_path}`
  await rm(bundle_dir, {
    recursive: true,
    force: true,
  })
  return bundle_path
}
