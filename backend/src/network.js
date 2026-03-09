import { configureDisplay } from "../../lib/scope.js"
import {
  getWiredIPAddress,
  onWiredConnectivityChange,
} from "../../lib/network.js"
import { reconfigureMediaMTX } from "../../lib/mediamtx.js"
import { reconfigureCockpit } from "../../lib/cockpit.js"
import os from "os"
import { publish } from "../../lib/mqtt.js"

const hostname = os.hostname()

let previous_address

async function updateDisplay(address) {
  let status = ""
  if (!address) status = "Offline"
  else if (address) status = `http://${address}`
  await configureDisplay({ status })
}

async function update() {
  const address = (await getWiredIPAddress()) || "192.168.4.1"
  if (address === previous_address) return
  await Promise.all([
    updateDisplay(address),
    reconfigureMediaMTX({ hostname, address }),
  ])
  await reconfigureCockpit({ hostname, address })
  previous_address = address
}

update()
onWiredConnectivityChange(update)

async function onExit() {
  // Clear retained message
  await publish("display", undefined, undefined, { retain: true })
  process.exit(0)
}

process.on("SIGINT", onExit)
process.on("SIGTERM", onExit)
