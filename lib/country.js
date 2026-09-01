import { readFile, writeFile } from "node:fs/promises"

import { $ } from "./exec.js"

import { updateSoftwareConfig } from "./file-config.js"

// We don't use files from "sudo dpkg-query -L wireless-regdb"
// because the tool to read them crda was removed in Bookworm
export async function getWifiRegulatoryDomains() {
  const iso3166tab = await readFile("/usr/share/zoneinfo/iso3166.tab", {
    encoding: "utf8",
  })
  let countries = []
  for (const line of iso3166tab.split("\n")) {
    if (line.startsWith("#")) continue
    const [value, label] = line.split("\t")
    if (value && label) {
      countries.push({ value, label })
    }
  }
  countries = countries.sort((a, b) => {
    return a.label.localeCompare(b.label)
  })

  return countries
}

const path = "/etc/modprobe.d/cfg80211_regdomain.conf"

export async function setWifiRegulatoryDomain(code) {
  // apply immediately and check the code is valid
  await $`sudo iw reg set ${code}`
  // make it persistent
  await writeFile(path, `options cfg80211 ieee80211_regdom=${code}`)
  // save configuration
  await updateSoftwareConfig({ ieee80211_regdom: code })
}

export async function getWifiRegulatoryDomain() {
  let data

  try {
    data = await readFile(path, {
      encoding: "utf8",
    })
  } catch (err) {
    if (err.code !== "ENOENT") throw err
    data = ""
  }

  const result = data.match(/options cfg80211 ieee80211_regdom=(.*$)/)
  return result?.[1] || null
}
