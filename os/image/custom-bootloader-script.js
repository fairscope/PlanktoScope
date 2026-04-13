#!/usr/bin/env node

import assert from "node:assert"
import { umount } from "./lib.js"
import { $ } from "execa"
import { readFile } from "node:fs/promises"
import { parse, stringify } from "ini"
import { getBlockDevices } from "./lib.js"

const device = "/dev/nvme0n1"
const systemconf = new URL(import.meta.resolve("./system.conf"))
// FIXME: rename partition to BOOTLOADERFS ?
// and mount to /mnt/bootloader ?
const autoboottxt = "/autoboot/autoboot.txt"

// https://rauc.readthedocs.io/en/latest/integration.html#custom-bootloader-backend-interface

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

async function getRaucSlot(boot_partition_number) {
  const partitions = await getBlockDevices("/dev/nvme0n1")
  const partition = partitions.find(
    ({ partn }) => partn === boot_partition_number,
  )
  if (!partition) {
    throw new Error(
      `Could not find /dev/nvme0n1 partition number "${partition_number}".`,
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

async function getBootPartitionNumber(rauc_slot) {
  const rauc_config = await readRaucSystemConf()
  const rauc_part = Object.values(rauc_config.slots).find(
    ({ bootname }) => bootname === rauc_slot,
  )
  if (!rauc_part?.device) {
    throw new Error(`Could not find rauc slot "${rauc_slot}"`)
  }

  const partitions = await getBlockDevices("/dev/nvme0n1")
  const partition = partitions.find(({ path }) => path === rauc_part.device)
  if (!partition) {
    throw new Error(`Could not find ${rauc_part.device} partition.`)
  }

  return partition.partn
}

async function getBootedSlot() {
  const { stdout: booted_partition_number } =
    await $`fdtget /sys/firmware/fdt /chosen/bootloader partition`
  return await getRaucSlot(parseInt(booted_partition_number, 10))
}

// https://github.com/Rtone/raspberrypi-firmware-rauc-bootloader-backend/blob/c8aa8ab78f9eb12c42d5b45f7d27c430bce8b7ef/bootloader-custom-backend#L225
async function set_primary_temporary() {
  await $`vcmailbox 0x00038064 4 0 1`
}

export const handlers = {
  // To get the primary slot, the handler is called with the argument get-primary.
  // The handler must output the current primary slot’s bootname on the stdout, and return 0 on exit,
  // if no error occurred. In case of failure, the handler must return with non-zero value.
  async ["get-primary"]() {
    const content = await readFile(autoboottxt, "utf8")
    const conf = parse(content)
    const boot_partition = conf?.all.boot_partition
    if (!boot_partition) {
      throw new Error(`Could not read all.boot_partition from "${systemconf}"`)
    }
    return await getRaucSlot(parseInt(boot_partition, 10))
  },
  // Accordingly, in order to set the primary slot, the custom bootloader handler is called with argument set-primary <slot.bootname>
  // where <slot.bootname> matches the bootname= key defined for the respective slot in your system.conf.
  // If the set was successful, the handler must also return with a 0, otherwise the return value must be non-zero.
  async ["set-primary"](bootname) {
    const boot_partition_number = await getBootPartitionNumber(bootname)
    const content = await readFile(autoboottxt, "utf8")
    const data = parse(content)
    const current_boot_partition = data.all.boot_partition
    data.all.boot_partition = current_boot_partition
    data.tryboot.boot_partition = boot_partition_number

    await $`vcmailbox 0x00038064 4 0 1`

    try {
      // TODO: atomic!
      await writeFile(autoboottxt, stringify(data))
    } catch {
      await $`vcmailbox 0x00038064 4 0 1`
    }
  },
  // In addition to the primary slot, RAUC must also be able to determine the boot state of a specific slot.
  // RAUC determines the necessary boot state by calling the custom bootloader handler with the argument get-state <slot.bootname>.
  // Whereupon the handler has to output the state good or bad to stdout and exit with the return value 0.
  // If the state cannot be determined or another error occurs, the custom bootloader handler must exit with non-zero return value.
  async ["get-state"](bootname) {
    const booted_slot = await getBootedSlot()
    if (bootname === booted_slot) return "good"

    const { stdout: tryboot_flag } =
      await $`fdtget /sys/firmware/fdt /chosen/bootloader tryboot`
    if (tryboot_flag === "1") return "good"

    return "bad"
  },
  // To set the boot state to the desire slot, the handler is called with argument set-state <slot.bootname> <state>.
  // As already mentioned in the paragraph above, the <slot.bootname> matches the bootname= key defined for the respective slot in your system.conf.
  // The <state> argument corresponds to one of the following values:
  //   * good if the last start of the slot was successful or
  //   * bad if the last start of the slot failed.
  // The return value must be 0 if the boot state was set successfully, or non-zero if an error occurred.
  async ["set-state"](bootname, state) {
    const boot_partition_number = await getBootPartitionNumber(bootname)

    const content = await readFile(autoboottxt, "utf8")
    const data = parse(content)

    const current_boot_partition = data.all.boot_partition
    const current_tryboot_partition = data.tryboot_boot_partition

    if (state === "good") {
      data.all.boot_partition = boot_partition_number
      // FIXME: other
      data.tryboot.boot_partition = current_boot_partition
    } else if (state === "bad") {
      // FIXME: other
      data.all.boot_partition = current_tryboot_partition
      data.tryboot.boot_partition = current_boot_partition
    }

    // TODO: atomic!
    await writeFile(autoboottxt, stringify(data))
  },
  // To get the current running slot, the handler must be called with the argument get-current.
  // The handler must output the current running slot’s bootname on the stdout, and return 0 on exit, if no error occurred.
  // Implementing this is only needed when the /proc/cmdline is not providing information about current booted slot.
  // https://github.com/Rtone/raspberrypi-firmware-rauc-bootloader-backend/blob/c8aa8ab78f9eb12c42d5b45f7d27c430bce8b7ef/bootloader-custom-backend#L461
  async ["get-current"]() {
    return getBootedSlot()
  },
}

if (import.meta.main) {
  if (process.getuid() !== 0) {
    throw new Error("Please run as root.")
  }

  console.debug(process.argv)

  const [, , command, ...args] = process.argv

  if (!(command in handlers)) {
    throw new Error(`Unknown handler "${command}".`)
  }

  const value = await handlers[command](...args)
  if (typeof value === "string") {
    process.stdout.write(value)
  }
  process.exit(0)
}
