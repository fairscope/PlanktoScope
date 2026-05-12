#!/usr/bin/env node

import assert from "node:assert"
import { $ } from "execa"
import { rm } from "node:fs/promises"

if (import.meta.main) {
  if (process.getuid() !== 0) {
    throw new Error("Please run as root.")
  }

  // https://systemd.io/BUILDING_IMAGES/
  await rm(`/var/lib/systemd/random-seed`, { force: true })
  await rm(`/var/lib/systemd/credential.secret`, { force: true })

  // ssh host keys
  await $("rm -f /etc/ssh/ssh_host_*_key*", { shell: true })

  // cache
  await rm("/var/cache/apt", { force: true, recursive: true })
  // 2GB swap file
  await rm("/var/swap", { force: true, recursive: true })

  // await rm("/opt/PlanktoScope/documentation", { force: true, recursive: true })
  // await rm("/opt/PlanktoScope/hardware", { force: true, recursive: true })
  // await rm("/opt/PlanktoScope/.git", { force: true, recursive: true })
}
