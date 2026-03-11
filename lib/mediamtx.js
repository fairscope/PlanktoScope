import { readFile, writeFile } from "node:fs/promises"
import os from "os"
import { queue } from "./helpers.js"

const config_template_path =
  "/home/pi/PlanktoScope/os/mediamtx/mediamtx.template.yml"
const config_path = "/home/pi/PlanktoScope/os/mediamtx/mediamtx.yml"

async function configureMediaMTX({ hostname, address } = {}) {
  let content = await readFile(config_template_path, "utf8")
  if (address) {
    content = content.replaceAll("192.0.2.1", address)
  }
  if (hostname) {
    content = content.replaceAll("raspberrypi", hostname)
  }
  await writeFile(config_path, content)
}

export const reconfigureMediaMTX = queue(
  async function reconfigureMediaMTX(config) {
    await configureMediaMTX(config)
    // mediamtx watches for file change on the config file
    // so we don't need to reload/restart the service
  },
)

/* eslint-disable n/no-top-level-await */
if (import.meta.main) {
  const hostname = os.hostname()
  await reconfigureMediaMTX({ hostname, address: "192.0.2.1" })
}
