#!/usr/bin/env node

// use "lsblk -d -o +path,ID,model" to find the device path
// sudo NODE_DEBUG=execa ./install-rpios-to-slot.js /dev/sdb

import assert from "node:assert"
import { umount, getMountPoint } from "../lib.js"
import { $ } from "execa"
import {
  setupRaspberryPiOSDevice,
  teardownRaspberryPiOSDevice,
} from "../rpios.js"
import {
  createPartitions,
  updateMountpoints,
  getPartitions,
  create_firmwarefs,
  create_rootfs,
  setup_cmdline,
  setup_cloudinit,
  setup_fstab,
  setup_machineid,
} from "../planktoscope.js"

if (import.meta.main) {
  if (process.getuid() !== 0) {
    throw new Error("Please run as root.")
  }

  const [, , device, bootname] = process.argv
  assert.ok(device)
  assert.ok(bootname)
  // await umount(device)

  let rpios_device, rpios_partitions, partitions
  try {
    ;[rpios_device, rpios_partitions] = await setupRaspberryPiOSDevice()

    partitions = await getPartitions(device)
    partitions = {
      BOOTLOADER: partitions.BOOTLOADER,
      [`FIRMWARE_${bootname}`]: partitions[`FIRMWARE_${bootname}`],
      [`ROOT_${bootname}`]: partitions[`ROOT_${bootname}`],
      DATA: partitions.DATA,
    }

    const mountpoint = await getMountPoint(partitions.BOOTLOADER.partlabel)
    await $`mount ${partitions.BOOTLOADER.path} ${mountpoint}`

    const rpios_bootfs = rpios_partitions["bootfs"]
    await create_firmwarefs(partitions[`FIRMWARE_${bootname}`], rpios_bootfs)
    const rpios_rootfs = rpios_partitions["rootfs"]
    await create_rootfs(partitions[`ROOT_${bootname}`], rpios_rootfs)

    partitions = await getPartitions(device)
    partitions = {
      BOOTLOADER: partitions.BOOTLOADER,
      [`FIRMWARE_${bootname}`]: partitions[`FIRMWARE_${bootname}`],
      [`ROOT_${bootname}`]: partitions[`ROOT_${bootname}`],
      DATA: partitions.DATA,
    }

    await setup_cmdline(rpios_partitions, partitions)
    await setup_cloudinit(rpios_partitions, partitions)
    await setup_fstab(partitions)
    await setup_machineid(partitions)
    // await updateMountpoints(device, rpios_partitions)
  } finally {
    await $`sync`
    // await umount(device)
    rpios_device && (await teardownRaspberryPiOSDevice(rpios_device))
    await Promise.all(
      Object.values(partitions).map((part) => umount(part.path)),
    )
  }

  console.log("✅ Slot is ready.")
}
