#!/usr/bin/env node

import { readFile, writeFile, appendFile } from "node:fs/promises"
import { join } from "node:path"
import { fileURLToPath } from "node:url"

import { $ } from "execa"

async function remountReadWrite(path) {
  const { stdout } = await $`findmnt --json --target ${path}`
  const result = JSON.parse(stdout)
  const filesystem = result.filesystems[0]
  const read_only = filesystem.options.split(",").includes("ro")

  if (read_only) {
    await $`mount -o remount,rw ${filesystem.target}`
  }
  return [read_only, filesystem]
}

async function remountReadWriteOnce(path, fn) {
  const [was_read_only, filesystem] = await remountReadWrite(path)

  try {
    await fn()
  } finally {
    if (was_read_only) {
      await $`mount -o remount,ro ${filesystem.target}`
    }
  }
}

const path = "/boot/firmware/"

// Configure firmware
// https://www.raspberrypi.com/documentation/computers/config_txt.html
async function process_config() {
  const path_config = join(path, "config.txt")

  const content = await readFile(path_config, "utf8")
  const include = await readFile(
    fileURLToPath(import.meta.resolve("./config.ini")),
    "utf8",
  )

  if (!content.trim().includes(include.trim())) {
    await appendFile(path_config, include)
  }
}

async function process_cmdline(path) {
  // Disable the 4 Raspberry logo in the top left corner
  // more space for kernel and system logs
  const content = await readFile(path, "utf8")
  const args = content.trim().split(" ")
  if (!args.includes("logo.nologo")) {
    args.push("logo.nologo")
  }
  await writeFile(path, args.join(" "))
}

if (import.meta.main) {
  await remountReadWriteOnce(path, async () => {
    await process_config()

    for (const cmdline of ["cmdline.txt", "cmdline-A.txt", "cmdline-B.txt"]) {
      try {
        await process_cmdline(join(path, "cmdline.txt"))
      } catch (err) {
        if (err.code !== "ENOENT") throw err
      }
    }
  })
}
