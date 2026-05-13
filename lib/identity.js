import { readFile, writeFile } from "fs/promises"
import ini from "ini"
import { fileURLToPath } from "url"
import { configureMediaMTX } from "./mediamtx.js"
import { configureCockpit } from "./cockpit.js"
import { $ } from "execa"

const path = "/run/machine-name"

export async function getName() {
  const data = await readFile(path, {
    encoding: "utf8",
  })

  return data.trim()
}

export async function getHostname() {
  return os.hostname()
}

export async function updateName(name) {
  await updateWifiSSD(name)

  const hostname = `planktoscope-${name}`
  await $`hostnamectl hostname ${hostname}`
  await updateHosts(hostname)
  await updateMediamtx(hostname)
  await updateCockpit(hostname)
}

async function updateWifiSSD(name) {
  const path =
    "/etc/NetworkManager/system-connections/wlan0-hotspot.nmconnection"

  const content = await readFile(path, "utf8")
  const conn = ini.parse(content)
  conn.wifi.ssid = `PlanktoScope ${name}`

  await writeFile(path, ini.stringify(conn))
}

async function updateMediamtx(hostname) {
  await configureMediaMTX({ hostname })
}

async function updateCockpit(hostname) {
  await configureCockpit({ hostname })
}

async function updateHosts(hostname) {
  let hosts = await readFile(
    fileURLToPath(import.meta.resolve("../os/network/hosts")),
    "utf8",
  )
  hosts = hosts.replaceAll("raspberrypi", hostname)
  await writeFile("/etc/hosts", hosts)
}
