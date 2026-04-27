import { readFile } from "node:fs/promises"
import { join } from "node:path"

import { $ } from "execa"
import { parse, stringify } from "ini"
import writeFileAtomic from "write-file-atomic"

const path_autoboot = "/bootloader/autoboot.txt"

export async function readAutoboot() {
  const content = await readFile(path_autoboot, "utf8")
  const autoboot = parse(content)

  autoboot.all ??= {}
  const boot_partition = autoboot?.all?.boot_partition
  if (typeof boot_partition === "string") {
    const n = Number(boot_partition)
    if (!Number.isInteger(n))
      throw new Error(
        `Invalid value "${boot_partition}" for all.boot_partition.`,
      )
    autoboot.all.boot_partition = n
  }

  autoboot.tryboot ??= {}
  const tryboot_partition = autoboot?.tryboot?.boot_partition
  if (typeof tryboot_partition === "string") {
    const n = Number(tryboot_partition)
    if (!Number.isInteger(n))
      throw new Error(
        `Invalid value "${tryboot_partition}" for tryboot.boot_partition.`,
      )
    autoboot.tryboot.boot_partition = n
  }

  return autoboot
}

export async function writeAutoboot(autoboot) {
  const { stdout } = await $`findmnt --json --target ${path_autoboot}`
  const result = JSON.parse(stdout)
  const filesystem = result.filesystems[0]
  const read_only = filesystem.options.split(",").includes("ro")

  const content = stringify(autoboot)

  if (read_only) {
    await $`mount -o remount,rw ${filesystem.target}`
  }
  try {
    await writeFileAtomic(path_autoboot, content)
  } finally {
    if (read_only) {
      await $`mount -o remount,ro ${filesystem.target}`
    }
  }
}

// https://github.com/rauc/rauc/pull/1599/changes#diff-919dcf951e9ecb449e0cfa6368b4c3dd441a4cad667abc4c59c97589f12c430bR190
// https://github.com/Rtone/raspberrypi-firmware-rauc-bootloader-backend/blob/c8aa8ab78f9eb12c42d5b45f7d27c430bce8b7ef/bootloader-custom-backend#L225
export async function setTryBootFlag(bool) {
  await $`vcmailbox 0x00038064 4 0 ${bool ? "1" : "0"}`
}

export async function getBootedPartitionNumber() {
  const { stdout } =
    await $`fdtget /sys/firmware/fdt /chosen/bootloader partition`
  const n = Number(stdout.trim())
  if (!Number.isInteger(n)) throw new Error("Could not get booted partition")
  return n
}

export async function getBootedWithTryBootFlag() {
  const { stdout } =
    await $`fdtget /sys/firmware/fdt /chosen/bootloader tryboot`
  const n = Number(stdout.trim())
  if (![0, 1].includes(n)) throw new Error("Could not get booted partition")
  return !!n
}

// ⚠️ DO NOT USE
// FIXME: This fails with "ioctl_set_msg failed:-1"
// even though it is used in https://github.com/rauc/rauc/pull/1599/changes#diff-919dcf951e9ecb449e0cfa6368b4c3dd441a4cad667abc4c59c97589f12c430bR124
// eslint-disable-next-line no-unused-vars
async function getTryBootFlag() {
  const { stdout } = await $`vcmailbox 0x00038064 4 0`
  /*
   * Parse output.
   *
   * If the reboot flag is unset:
   *
   * 	$ vcmailbox 0x00030064 4 0 0
   * 	0x0000001c 0x80000000 0x00030064 0x00000004 0x80000004 0x00000000 0x00000000
   *
   * If the reboot flag is set:
   *
   * 	$ vcmailbox 0x00030064 4 0 0
   * 	0x0000001c 0x80000000 0x00030064 0x00000004 0x80000004 0x00000001 0x00000000
   */

  const [, , , , word] = stdout.split(" ")
  const value = parseInt(word, 0) >>> 0 // >>> 0 coerces to uint32
  return value !== 0
}

export async function getRaspberryPiOSReference(base_path = "/") {
  const path = join(base_path, "/etc/rpi-issue")
  const content = await readFile(path, "utf8")
  const ref = content.match(/Raspberry Pi reference (.*)/)?.[1]
  if (!ref) throw new Error("Could not read reference from /etc/rpi-issue")
  return ref
}
