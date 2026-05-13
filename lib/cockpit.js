import { readFile, writeFile } from "node:fs/promises"
import os from "os"
import { Systemctl } from "systemctl.js"
import { queue } from "./helpers.js"
import ini from "ini"
import { getWiredAddress } from "./helpers.js"

const config_path = "/etc/cockpit/cockpit.conf"

export async function configureCockpit({ hostname, address } = {}) {
  const config = ini.parse(await readFile(config_path, "utf8"))

  const origins = config.WebService.Origins.trim().split(" ")

  if (address) {
    origins[0] = `http://${address}`
  }
  if (hostname) {
    origins[1] = `http://${hostname}`
    origins[2] = `http://${hostname}.local`
  }

  config.WebService.Origins = origins.join(" ")

  await writeFile(config_path, ini.stringify(config))
}

async function restartCockpit() {
  const systemctl = new Systemctl()
  await systemctl.init()
  await systemctl.restart("cockpit")
  await systemctl.deinit()
}

export const reconfigureCockpit = queue(
  async function reconfigureCockpit(config) {
    await configureCockpit(config)
    await restartCockpit()
  },
)

/* eslint-disable n/no-top-level-await */
if (import.meta.main) {
  const hostname = os.hostname()
  const address = getWiredAddress()
  await reconfigureCockpit({ hostname, address })
  // eslint-disable-next-line n/no-process-exit
  process.exit(0)
}
