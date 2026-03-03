import { configureDisplay } from "../../lib/scope.js"
import {
  getWiredIPAddress,
  onWiredConnectivityChange,
} from "../../lib/network.js"
import { reconfigureMediaMTX } from "../../lib/mediamtx.js"
import { reconfigureCockpit } from "../../lib/cockpit.js"
import os from "os"

async function updateDisplay(address) {
  let status = ""
  if (!address) status = "Offline"
  else if (address) status = `http://${address}`
  await configureDisplay({ status })
}

async function update() {
  const hostname = os.hostname()
  const address = await getWiredIPAddress()
  await Promise.all([
    updateDisplay(address),
    reconfigureMediaMTX({ hostname, address }),
  ])
  await reconfigureCockpit({ hostname, address })
}

update()
onWiredConnectivityChange(update)
