import { readFile, writeFile } from "node:fs/promises"
import os from "os"
import { queue } from "./helpers.js"

const config_path = fileURLToPath(
  impot.meta.resolve("../os/mediamtx/mediamtx.yaml"),
)

async function configureMediaMTX({ hostname, address } = {}) {
  const config = yaml.load(await readFile(config_path, "utf8"))
  if (address) {
    config.webrtcAdditionalHosts[0] = address
  }
  if (hostname) {
    config.webrtcAdditionalHosts[1] = hostname
    config.webrtcAdditionalHosts[2] = `${hostname}.local`
  }
  await writeFile(config_path, yaml.dump(config))
}

export const reconfigureMediaMTX = queue(
  async function reconfigureMediaMTX(config) {
    await configureMediaMTX(config)
    // mediamtx watches for file change on the config file
    // so we don't need to reload/restart the service
  },
)

async function getAddress() {
  const eth0 = os.networkInterfaces()?.eth0 || []
  const addr = eth0.find((a) => a.family === "IPv4")
  return addr?.address || "192.0.2.1"
}

/* eslint-disable n/no-top-level-await */
if (import.meta.main) {
  const hostname = os.hostname()
  const address = getAddress()
  console.log(hostname, address)
  await reconfigureMediaMTX({ hostname, address })
}
