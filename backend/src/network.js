import { configureDisplay } from "../../lib/scope.js"
import { wired_controller } from "../../lib/network/network.js"
import { reconfigureMediaMTX } from "../../lib/mediamtx.js"
import { reconfigureCockpit } from "../../lib/cockpit.js"
import os from "os"
import { publish } from "../../lib/mqtt.js"

async function updateDisplay(address) {
  let status = ""
  if (!address) status = "Offline"
  else if (address) status = `http://${address}`
  await configureDisplay({ status })
}

wired_controller.subscribe({
  next: (address) => {
    address ??= "192.168.4.1"
    const hostname = os.hostname()
    Promise.all([
      updateDisplay(address),
      reconfigureMediaMTX({ hostname, address }),
      reconfigureCockpit({ hostname, address }),
    ]).catch(console.error)
  },
})

async function onExit() {
  // Clear retained message to avoid displaying an old ip address on first boot
  await publish("display", undefined, undefined, { retain: true })
  process.exit(0)
}

process.on("SIGINT", onExit)
process.on("SIGTERM", onExit)
