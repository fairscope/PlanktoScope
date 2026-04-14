#!/usr/bin/env node

import assert from "node:assert"

import { parse, stringify } from "ini"

import {
  setTryBootFlag,
  getBootedWithTryBootFlag,
  readAutoboot,
  writeAutoboot,
} from "./rpi.js"
import { getRaucSlot, getBootPartitionNumber, getBootedSlot } from "./rauc.js"

// https://rauc.readthedocs.io/en/latest/integration.html#custom-bootloader-backend-interface

export const handlers = {
  // To get the primary slot, the handler is called with the argument get-primary.
  // The handler must output the current primary slot’s bootname on the stdout, and return 0 on exit,
  // if no error occurred. In case of failure, the handler must return with non-zero value.
  async ["get-primary"]() {
    const autoboot = await readAutoboot()
    const boot_partition = autoboot?.all?.boot_partition
    if (!Number.isInteger(boot_partition)) {
      throw new Error(`Could not read autoboot.all.boot_partition.`)
    }
    return await getRaucSlot(n)
  },
  // Accordingly, in order to set the primary slot, the custom bootloader handler is called with argument set-primary <slot.bootname>
  // where <slot.bootname> matches the bootname= key defined for the respective slot in your system.conf.
  // If the set was successful, the handler must also return with a 0, otherwise the return value must be non-zero.
  async ["set-primary"](bootname) {
    const boot_partition_number = await getBootPartitionNumber(bootname)
    const other_boot_partition_number = await getBootPartitionNumber(
      bootname === "A" ? "B" : "A",
    )
    const autoboot = await readAutoboot()
    autoboot.all.boot_partition = other_boot_partition_number
    autoboot.tryboot.boot_partition = boot_partition_number

    await setTryBootFlag(true)

    try {
      await writeAutoboot(autoboot)
    } catch {
      await setTryBootFlag(false)
    }
  },
  // In addition to the primary slot, RAUC must also be able to determine the boot state of a specific slot.
  // RAUC determines the necessary boot state by calling the custom bootloader handler with the argument get-state <slot.bootname>.
  // Whereupon the handler has to output the state good or bad to stdout and exit with the return value 0.
  // If the state cannot be determined or another error occurs, the custom bootloader handler must exit with non-zero return value.
  async ["get-state"](bootname) {
    const booted_slot = await getBootedSlot()
    if (bootname === booted_slot) return "good"
    if (await getBootedWithTryBootFlag()) return "good"
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
    const other_boot_partition_number = await getBootPartitionNumber(
      bootname === "A" ? "B" : "A",
    )

    const autoboot = await readAutoboot()

    if (state === "good") {
      autoboot.all.boot_partition = boot_partition_number
      autoboot.tryboot.boot_partition = other_boot_partition_number
    } else if (state === "bad") {
      autoboot.all.boot_partition = other_boot_partition_number
      delete autoboot.tryboot.boot_partition
      // FIXME: also remove the tryboot flag
      // FIXME: try it boots to all.boot_partition in this case still
    }

    await writeAutoboot(autoboot)
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
