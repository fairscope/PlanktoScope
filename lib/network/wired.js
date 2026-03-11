/* eslint-disable n/no-top-level-await */

import { systemBus } from "dbus.js"
import { execa } from "execa"
import { queue } from "../helpers.js"
import { readProperty, watchProperty } from "../dbus-helpers.js"

// NetworkManager "Ip4Connectivity" and "NMConnectivityState" is misleading
// it only updates when/if
//   * there is an IP configured (manually or via DHCP)
//   * the cable is physically unplugged
// it does not "watch" for connectivity changes with the DHCP server or gateway
// so we have this whole thing to ping the gateway at regular interval when we have an IP address

const service = systemBus().getService("org.freedesktop.NetworkManager")

const NetworkManager = await service.getInterface(
  "/org/freedesktop/NetworkManager",
  "org.freedesktop.NetworkManager",
)

const wired_interface = "eth0"
const [wired_device_path] =
  await NetworkManager.GetDeviceByIpIface(wired_interface)
const wired_device = await service.getInterface(
  wired_device_path,
  "org.freedesktop.NetworkManager.Device",
)

async function getWiredConnectivity() {
  const IP4Config_path = await readProperty(wired_device, "Ip4Config")
  const IP4Config = await service.getInterface(
    IP4Config_path,
    "org.freedesktop.NetworkManager.IP4Config",
  )

  const [gateway, addressData] = await Promise.all([
    readProperty(IP4Config, "Gateway"),
    readProperty(IP4Config, "AddressData"),
  ])
  const address = addressData?.[0]?.find?.(
    (list) => list?.[0] === "address",
  )?.[1]?.[1]?.[0]

  return { address, gateway }
}

async function pingWired(host) {
  try {
    await execa("ping", ["-c", "1", "-I", wired_interface, host])
    return true
  } catch {
    return false
  }
}

export const wired_controller = new Observable(async (subscriber) => {
  let current_address = undefined
  let ping_interval = null

  function nextValue(val = null) {
    if (current_address === val) return
    subscriber.next(val)
    current_address = val
  }

  async function testGateway({ gateway, address }) {
    try {
      nextValue((await pingWired(gateway)) ? address : null)
    } catch (err) {
      console.error(err)
    }
  }

  async function handleDHCP(dhcp) {
    await testGateway(dhcp)
    ping_interval = setInterval(() => testGateway(dhcp), 5000)
  }

  const getConnectivity = queue(async () => {
    const { address, gateway } = await getWiredConnectivity()
    if (!gateway || !address) {
      return nextValue(null)
    }

    handleDHCP({ address, gateway })
  })

  // https://networkmanager.dev/docs/api/latest/nm-dbus-types.html#NMConnectivityState
  const states = {
    UNKNOWN: 0,
    NONE: 1,
    PORTAL: 2,
    LIMITED: 3,
    FULL: 4,
  }
  watchProperty(wired_device, "Ip4Connectivity").subscribe({
    next(val) {
      clearInterval(ping_interval)
      if ([states.FULL || states.LIMITED].includes(val)) {
        getConnectivity().catch(console.error)
      } else {
        nextValue(null)
      }
    },
  })
})

if (import.meta.main) {
  wired_controller.subscribe({
    next: async (value) => {
      console.log(value)
    },
  })
}
