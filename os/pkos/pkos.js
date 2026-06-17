#!/usr/bin/env node

import { $ } from "execa"
import { getBootPartitionNumber, getRaucSlot } from "../rauc/rauc.js"
import { getBootedPartitionNumber } from "../image/rpi.js"
import { mount_active_firmware } from "../image/mount-firmware.js"

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
  } else {
    throw new Error(`Unknwon command "${command}".`)
  }
}
