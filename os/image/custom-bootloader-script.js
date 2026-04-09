#!/usr/bin/env node

import assert from "node:assert"
import { umount } from "./lib.js"
import { $ } from "execa"
// import {
//   setupRaspberryPiOSDevice,
//   mountRaspberryPiOSPartitions,
//   teardownRaspberryPiOSDevice,
// } from "./rpios.js"
// import { createPartitions, updateMountpoints } from "./planktoscope.js"

if (import.meta.main) {
  if (process.getuid() !== 0) {
    throw new Error("Please run as root.")
  }

  console.log(process.argv)

  const [, , device] = process.argv
  assert.ok(device)
}
