import { readFile, writeFile } from "node:fs/promises"
import os from "os"
import { $ } from "execa"
import { Systemctl } from "systemctl.js"

const config_template_path = "/home/pi/PlanktoScope/os/cockpit/cockpit.ini"
const config_tmp_path = "/tmp/cockpit.conf"
const config_path = "/etc/cockpit/cockpit.conf"

async function configureCockpit({ hostname, address } = {}) {
  let content = await readFile(config_template_path, "utf8")
  if (address) {
    content = content.replaceAll("192.0.2.1", address)
  }
  if (hostname) {
    content = content.replaceAll("raspberrypi", hostname)
  }
  await writeFile(config_tmp_path, content)
  // FIXME: We should not need sudo, let's figure out
  // how we can write cockpit config without root
  await $`sudo mv ${config_tmp_path} ${config_path}`
}

async function restartCockpit() {
  const systemctl = new Systemctl()
  await systemctl.init()
  await systemctl.restart("cockpit")
  await systemctl.deinit()
}

export async function reconfigureCockpit(config) {
  await configureCockpit(config)
  await restartCockpit()
}

/* eslint-disable n/no-top-level-await */
if (import.meta.main) {
  const hostname = os.hostname()
  await reconfigureCockpit({ hostname, address: "10.42.0.94" })
}
