#!/usr/bin/env node

import { $ } from "execa"

const device = `/dev/nvme0n1`
const partn = 6
const path = device + "p" + partn

if (import.meta.main) {
  if (process.getuid() !== 0) {
    throw new Error("Please run as root.")
  }

  // await $`mount ${path} /mnt`
  // await $`fstrim /mnt`
  // await $`umount ${path}`

  // Resize is not effective, it creates a smaller partition
  await $`e2fsck -f ${path}`
  await $`resize2fs -M ${path}`
  // await $`sgdisk --delete=${partn} --new=${partn}:0:+512M --typecode=${partn}:8300 -A ${partn}:set:0 -A ${partn}:set:1 -A ${partn}:set:62 -A ${partn}:set:63 --change-name=${partn}:DATA --partition-guid=${partn}:ce528120-d0dd-52be-aea3-8225fabd8a00 ${device}`

  // systemd-repart will recreate the partition on boot
  // await $`wipefs -a ${path}`
  // await $`sgdisk --delete=${partn} ${device}`
  //
  await $`partprobe ${device}`
}
