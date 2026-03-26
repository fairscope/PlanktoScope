#!/usr/bin/env node

// use "lsblk -d -o +path,ID,model" to find the device path
// sudo NODE_DEBUG=execa ./make-disk.js /dev/sdb

import assert from "node:assert"
import { umount } from "./lib.js"
import { $ } from "execa"
import {
  setupRaspberryPiOSDevice,
  mountRaspberryPiOSPartitions,
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

  let [rpios_device, rpios_partitions] = await setupRaspberryPiOSDevice()

  try {
    // With partclone the source cannot be mounted so we mount them after
    await createPartitions(device, rpios_partitions)
    rpios_partitions = await mountRaspberryPiOSPartitions(
      rpios_device,
      rpios_partitions,
    )
    await updateMountpoints(device, rpios_partitions)
    console.log("✅ Disk is ready.")
  } finally {
    await $`sync`
    await umount(device)
    await teardownRaspberryPiOSDevice(rpios_device)
  }
}
