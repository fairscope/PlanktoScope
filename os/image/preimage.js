#!/usr/bin/env node

import { $ } from "execa"
import { rm, writeFile, copyFile, chown } from "node:fs/promises"
import { getCommit, getUrl } from "../../lib/software.js"
import { fileURLToPath } from "node:url"
import { setTimezone } from "../../lib/timezone.js"

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

  // remove machine-name
  await rm("/run/machine-name", { force: true })

  // restore hostname files
  await writeFile("/etc/hostname", "raspberrypi")
  await copyFile(
    fileURLToPath(import.meta.resolve("../network/hosts")),
    "/etc/hosts",
  )

  await copyFile(
    fileURLToPath(import.meta.resolve("../cockpit/cockpit.ini")),
    "/etc/cockpit/cockpit.conf",
  )
  await chown("/etc/cockpit/cockpit.conf", 1000, 1000)

  await copyFile(
    fileURLToPath(import.meta.resolve("../mediamtx/mediamtx.yaml")),
    "/etc/mediamtx.yaml",
  )
  await chown("/etc/mediamtx.yaml", 1000, 1000)

  const cfg80211_path = "/etc/modprobe.d/cfg80211_regdomain.conf"
  await copyFile(
    fileURLToPath(import.meta.resolve("../network/cfg80211_regdomain.conf")),
    cfg80211_path,
  )
  await chown(cfg80211_path, 1000, 1000)

  // reset wireless regulatory domain / country
  const wlan_path =
    "/etc/NetworkManager/system-connections/wlan0-hotspot.nmconnection"
  await copyFile(
    fileURLToPath(import.meta.resolve("../network/wlan0-hotspot.ini")),
    wlan_path,
  )
  await $`chown root:root ${wlan_path}`
  // "failed to load connection: File permissions (100644) are insecure"
  await $`chmod 0600 ${wlan_path}`

  // "reset" timezone
  await setTimezone("UTC")

  await rm("/opt/PlanktoScope/documentation", { force: true, recursive: true })
  await rm("/opt/PlanktoScope/hardware", { force: true, recursive: true })

  const [commit, url] = await Promise.all([getCommit(), getUrl()])
  await writeFile(
    "/opt/PlanktoScope/gitinfo.json",
    JSON.stringify({ commit, url }, null, 2),
  )

  await rm("/opt/PlanktoScope/node-red/projects/dashboard/.git", {
    force: true,
    recursive: true,
  })
  await rm("/opt/PlanktoScope/.git", { force: true, recursive: true })
}
