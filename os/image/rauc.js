import { readFile, writeFile } from "node:fs/promises"

import { parse, stringify } from "ini"

import { getBlockDevices } from "./lib.js"

// FIXME: nvme or sdcard
const device = "/dev/nvme0n1"
const systemconf = new URL(import.meta.resolve("./system.conf"))

export async function getBootedSlot() {
  const booted_partition_number = await getBootPartitionNumber()
  return await getRaucSlot(boot_partition_number)
}

export async function getRaucSlot(boot_partition_number) {
  const partitions = await getBlockDevices(device)
  const partition = partitions.find(
    ({ partn }) => partn === boot_partition_number,
  )
  if (!partition) {
    throw new Error(
      `Could not find ${device} partition number "${partition_number}".`,
    )
  }

  const rauc_config = await readRaucSystemConf()
  const rauc_part = Object.values(rauc_config.slots).find(
    ({ device }) => device === partition.path,
  )
  if (!rauc_part?.bootname) {
    throw new Error(`Could not find rauc slot for "${partition.path}"`)
  }

  return rauc_part.bootname
}

export async function getBootPartitionNumber(rauc_slot) {
  const rauc_config = await readRaucSystemConf()
  const rauc_part = Object.values(rauc_config.slots).find(
    ({ bootname }) => bootname === rauc_slot,
  )
  if (!rauc_part?.device) {
    throw new Error(`Could not find rauc slot "${rauc_slot}"`)
  }

  const partitions = await getBlockDevices(device)
  const partition = partitions.find(({ path }) => path === rauc_part.device)
  if (!partition) {
    throw new Error(`Could not find ${rauc_part.device} partition.`)
  }

  return partition.partn
}

async function readRaucSystemConf() {
  const content = await readFile(systemconf, "utf8")
  const conf = parse(content)

  // https://rauc.readthedocs.io/en/latest/reference.html#slot-slot-class-idx-sections
  const slot_entries = {}
  for (const [slot_class_name, slot_class] of Object.entries(conf.slot)) {
    for (const [slot_number, value] of Object.entries(slot_class)) {
      slot_entries[slot_class_name + "." + slot_number] = value
    }
  }

  conf.slots = slot_entries

  return conf
}
