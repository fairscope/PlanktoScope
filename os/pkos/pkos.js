#!/usr/bin/env node

import { $ } from "execa"
import { getBootPartitionNumber, getRaucSlot } from "../rauc/rauc.js"
import { getBootedPartitionNumber } from "../image/rpi.js"

async function reboot(slot) {
  await $`reboot ${await getBootPartitionNumber(slot)}`
}

async function slot() {
  const n = await getBootedPartitionNumber()
  return await getRaucSlot(n)
}

async function prepare() {
  await $`/opt/PlanktoScope/os/setup.sh`
  await $`/opt/PlanktoScope/os/postinstall.sh`
  await $`/opt/PlanktoScope/os/image/preimage.js`
}

if (import.meta.main) {
  if (process.getuid() !== 0) {
    throw new Error("Please run as root.")
  }

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
  } else {
    throw new Error(`Unknwon command "${command}".`)
  }
}
