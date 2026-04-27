#!/usr/bin/env node

import { $ } from "execa"

import { getBootedDevice, getBlockDevices } from "./lib.js"
import { getBootedPartitionNumber } from "./rpi.js"

async function is_mounted() {
  try {
    await $`findmnt /boot/firmware`
    return true
  } catch {
    return false
  }
}

async function get_firmware_partition() {
  const device = await getBootedDevice()
  const partition_number = await getBootedPartitionNumber()

  const partition = (await getBlockDevices(device)).find(
    (part) => part.partn === partition_number,
  )

  return partition
}

async function mount_active_firmware() {
  if (await is_mounted()) return
  const partition = await get_firmware_partition()
  await $`mount -o defaults,ro ${partition.path} /boot/firmware`
}

async function remount_read_write() {
  await $`mount -o remount,rw /boot/firmware`
}

async function remount_read_only() {
  await $`mount -o remount,ro /boot/firmware`
}

if (import.meta.main) {
  await mount_active_firmware()
}
