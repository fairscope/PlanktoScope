import { readFile, writeFile } from "node:fs/promises"
import os from "os"
import { Systemctl } from "systemctl.js"
import { queue } from "./helpers.js"
import ini from "ini"
import { getAddress } from "./network/wired.js"

const config_path = "/etc/cockpit/cockpit.conf"

async function configureCockpit({ hostname, address } = {}) {
  const config = ini.parse(await readFile(config_path, "utf8"))

  const origins = config.WebService.Origins.trim().split(" ")
  console.log(origins)

  if (address) {
    origins[0] = address
  }
  if (hostname) {
    origins[1] = hostname
    origins[2] = `${hostname}.local`
  }
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
  const address = getAddress()
  await reconfigureCockpit({ hostname, address })
}
