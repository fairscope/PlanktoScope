#!/usr/bin/env node

// use "lsblk -d -o +path,ID,model" to find the device path
// sudo NODE_DEBUG=execa ./make-disk.js /dev/sdb

import assert from "node:assert"
import { umount } from "./lib.js"
import { $ } from "execa"
import {
  setupRaspberryPiOSDevice,
  teardownRaspberryPiOSDevice,
} from "./rpios.js"
import { createPartitions, updateMountpoints } from "./planktoscope.js"

if (import.meta.main) {
  if (process.getuid() !== 0) {
    throw new Error("Please run as root.")
  }

  const [, , device] = process.argv
  assert.ok(device)
  await umount(device)

  let rpios_device, rpios_partitions
  try {
    ;[rpios_device, rpios_partitions] = await setupRaspberryPiOSDevice()
    await createPartitions(device, rpios_partitions)
    await updateMountpoints(device, rpios_partitions)
  } finally {
    await $`sync`
    await umount(device)
    rpios_device && (await teardownRaspberryPiOSDevice(rpios_device))
  }

  console.log("✅ Disk is ready.")
}
