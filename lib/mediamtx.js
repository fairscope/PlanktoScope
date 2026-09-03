import { readFile, writeFile } from "node:fs/promises"
import os from "os"
import { queue } from "./helpers.js"
import yaml from "js-yaml"
import { getWiredAddress } from "./helpers.js"

const config_path = "/etc/mediamtx.yaml"

export async function configureMediaMTX({ address } = {}) {
  const current = await readFile(config_path, "utf8")
  const config = yaml.load(current)
  if (address) {
    config.webrtcAdditionalHosts[0] = address
  }
  const rendered = yaml.dump(config)
  if (rendered === current) return
  await writeFile(config_path, rendered)
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
