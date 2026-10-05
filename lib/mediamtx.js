import { readFile, writeFile } from "node:fs/promises"
import os from "os"
import { queue } from "./helpers.js"
import yaml from "js-yaml"
import { getWiredAddress } from "./helpers.js"

const config_path = "/etc/mediamtx.yaml"

export async function configureMediaMTX({ hostname, address } = {}) {
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

if (import.meta.main) {
  const hostname = os.hostname()
  const address = getWiredAddress()
  /* eslint-disable-next-line n/no-top-level-await */
  await reconfigureMediaMTX({ hostname, address })
  // eslint-disable-next-line n/no-process-exit
  process.exit(0)
}
