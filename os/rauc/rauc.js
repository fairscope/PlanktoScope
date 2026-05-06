#!/usr/bin/env node

import { readFile, writeFile, rm, mkdir } from "node:fs/promises"

import { parse, stringify } from "ini"
import { $ } from "execa"

import { getBootedDevice, getBlockDevices } from "../image/lib.js"
import { getBootedPartitionNumber } from "../image/rpi.js"
import { fileURLToPath } from "node:url"
import { join } from "node:path"

const device = await getBootedDevice()

export async function getBootedSlot() {
  const booted_partition_number = await getBootedPartitionNumber()
  return await getRaucSlot(booted_partition_number)
}

export async function getRaucSlot(boot_partition_number) {
  const partitions = await getBlockDevices(device)
  const partition = partitions.find(
    ({ partn }) => partn === boot_partition_number,
  )
  if (!partition) {
    throw new Error(
      `Could not find ${device} partition number "${boot_partition_number}".`,
    )
  }

  const rauc_config = await readRaucSystemConf()
  let rauc_part = Object.values(rauc_config.slots).find(
    ({ device }) => device === partition.path,
  )
  if (rauc_part.parent) {
    rauc_part = rauc_config.slots[rauc_part.parent]
  }

  if (!rauc_part?.bootname) {
    throw new Error(`Could not find rauc slot for "${partition.path}"`)
  }

  return rauc_part.bootname
}

export async function getBootPartitionNumber(bootname) {
  const { slots } = await readRaucSystemConf()
  const [slot_name] = Object.entries(slots).find(
    ([, slot]) => slot.bootname === bootname,
  )
  const firmware_slot = Object.values(slots).find(
    (slot) => slot.parent === slot_name,
  )
  if (!firmware_slot) {
    throw new Error(`Could not find boot partition for "${bootname}"`)
  }

  const partitions = await getBlockDevices(device)
  const partition = partitions.find(({ path }) => path === firmware_slot.device)
  if (!partition) {
    throw new Error(`Could not find ${firmware_slot.device} partition.`)
  }

  return partition.partn
}

const systemconf = "/etc/rauc/system.conf"
export async function readRaucSystemConf(path = systemconf) {
  const content = await readFile(path, "utf8")
  const conf = parse(content)

  // https://rauc.readthedocs.io/en/latest/reference.html#slot-slot-class-idx-sections
  conf.slot ??= {}
  // FIXME: Remove conf.slots and read from slot instead in higher level fns
  const slot_entries = {}
  for (const [slot_class_name, slot_class] of Object.entries(conf.slot)) {
    for (const [slot_number, value] of Object.entries(slot_class)) {
      slot_entries[slot_class_name + "." + slot_number] = value
    }
  }

  conf.slots = slot_entries

  return conf
}

async function writeRaucSystemConf(conf, path = systemconf) {
  delete conf.slots

  const data = stringify(conf)
  await writeFile(path, data)
}

export async function setup_system_conf() {
  const partitions = await getBlockDevices(device)
  const conf = await readRaucSystemConf(new URL("./rauc.ini", import.meta.url))

  conf.slot["FIRMWARE"] ??= {}
  conf.slot["ROOT"] ??= {}
  ;["A", "B"].forEach((bootname, idx) => {
    const part_firmware = partitions.find(
      (part) => part.partlabel === `FIRMWARE_${bootname}`,
    )
    conf.slot["FIRMWARE"][idx] = {
      device: part_firmware.path,
      type: part_firmware.fstype,
      parent: `ROOT.${idx}`,
    }

    const part_root = partitions.find(
      (part) => part.partlabel === `ROOT_${bootname}`,
    )
    conf.slot["ROOT"][idx] = {
      bootname,
      device: part_root.path,
      type: part_root.fstype,
    }
  })

  await writeRaucSystemConf(conf)
}

export async function createBundle(device, bootname) {
  const date = new Date().toISOString()
  const build = date
  const version = date.split("T")[0]

  const partitions = await getBlockDevices(device)

  const manifest = parse(
    await readFile(
      fileURLToPath(import.meta.resolve("./manifest.ini")),
      "utf8",
    ),
  )

  const temp_dir = fileURLToPath(import.meta.resolve("./temp-dir"))
  await rm(temp_dir, {
    recursive: true,
    force: true,
  })
  await mkdir(temp_dir)
  const manifest_path = join(temp_dir, "manifest.raucm")
  manifest.update.build = build
  manifest.update.version = version
  await writeFile(manifest_path, stringify(manifest))

  const part_firmware = partitions.find(
    (part) => part.partlabel === `FIRMWARE_${bootname}`,
  )
  const part_root = partitions.find(
    (part) => part.partlabel === `ROOT_${bootname}`,
  )

  await $`dd if=${part_firmware.path} of=${join(temp_dir, manifest.image.FIRMWARE.filename)} bs=64M`

  // TODO: Create a img file instead with "mkfs.ext4 rootfs.img"
  // mount it as loop device "mount -o loop rootfs.img /mnt"
  // then rsync files into it
  await $`dd if=${part_root.path} of=${join(temp_dir, manifest.image.ROOT.filename)} bs=64M`
  await $`rauc --cert demo.cert.pem --key demo.key.pem bundle temp-dir/ PlanktoScope-update-${version}.raucb`
  await rm(temp_dir, {
    recursive: true,
    force: true,
  })
}

if (import.meta.main) {
  const [, , command, ...args] = process.argv
  if (command === "create-configuration") {
    await setup_system_conf()
  } else if (command === "create-bundle") {
    const [device_path, bootname] = args
    if (!device_path || !bootname) {
      throw new Error("create-bundle /dev/device A|B")
    }
    const booted_slot = await getBootedSlot()
    if (device_path === device && bootname === booted_slot) {
      throw new Error(
        `Cannot create a bundle for booted ${device} ${bootname} slot.`,
      )
    }
    await createBundle(device_path, bootname)
  } else {
    throw new Error(`Unknwon command "${command}".`)
  }
}
