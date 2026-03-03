/* eslint-disable n/no-top-level-await */

import { systemBus } from "dbus.js"

const service = systemBus().getService("org.freedesktop.NetworkManager")

const NetworkManager = await service.getInterface(
  "/org/freedesktop/NetworkManager",
  "org.freedesktop.NetworkManager",
)

const [device_path] = await NetworkManager.GetDeviceByIpIface("wlan0")

const [DeviceWireless, DeviceWireless_Properties] = await Promise.all([
  service.getInterface(
    device_path,
    "org.freedesktop.NetworkManager.Device.Wireless",
  ),
  service.getInterface(device_path, "org.freedesktop.DBus.Properties"),
])

export { DeviceWireless }

export async function scan() {
  const deferred = Promise.withResolvers()

  // > To know when the scan is finished, use the "PropertiesChanged" signal from "org.freedesktop.DBus.Properties" to listen to changes to the "LastScan" property.
  // https://networkmanager.dev/docs/api/latest/gdbus-org.freedesktop.NetworkManager.Device.Wireless.html#gdbus-method-org-freedesktop-NetworkManager-Device-Wireless.RequestScan
  function handler(interface_name, changed_properties) {
    if (interface_name !== "org.freedesktop.NetworkManager.Device.Wireless") {
      return
    }

    const LastScan = changed_properties.find((changed_property) => {
      const [property_name] = changed_property
      return property_name === "LastScan"
    })
    if (!LastScan) return

    DeviceWireless_Properties.unsubscribe("PropertiesChanged", handler).then(
      deferred.resolve,
      deferred.reject,
    )
  }
  await DeviceWireless_Properties.subscribe("PropertiesChanged", handler)

  await DeviceWireless.RequestScan({})

  return deferred.promise
}

async function readProp(iface, propName) {
  const bus = iface.$parent.service.bus
  const val = await bus.invoke({
    destination: iface.$parent.service.name,
    path: iface.$parent.name,
    interface: "org.freedesktop.DBus.Properties",
    member: "Get",
    signature: "ss",
    body: [iface.$name, propName],
  })
  return val[0][1][0]
}

export async function getWifis() {
  const [access_point_paths] = await DeviceWireless.GetAllAccessPoints()

  const access_points = await Promise.all(
    access_point_paths.map((access_point_path) => {
      return service.getInterface(
        access_point_path,
        "org.freedesktop.NetworkManager.AccessPoint",
      )
    }),
  )

  return Promise.all(
    access_points.map(async (access_point) => {
      const [Ssid, frequency, strength] = await Promise.all(
        ["Ssid", "Frequency", "Strength"].map((propName) =>
          readProp(access_point, propName),
        ),
      )
      const ssid = new TextDecoder().decode(Ssid)
      const path = access_point.$parent.name
      return { ssid, frequency, strength, path }
    }),
  )
}

export async function connectToWifi(path) {
  await NetworkManager.AddAndActivateConnection([], device_path, path)
}

const [wired_device_path] = await NetworkManager.GetDeviceByIpIface("eth0")
const [wired_device, wired_device_Properties] = await Promise.all([
  service.getInterface(
    wired_device_path,
    "org.freedesktop.NetworkManager.Device",
  ),
  service.getInterface(wired_device_path, "org.freedesktop.DBus.Properties"),
])

export async function getWiredIPAddress() {
  const IP4Config_path = await readProp(wired_device, "Ip4Config")
  const IP4Config = await service.getInterface(
    IP4Config_path,
    "org.freedesktop.NetworkManager.IP4Config",
  )
  const addressData = await readProp(IP4Config, "AddressData")
  const address = addressData?.[0]?.[0]?.[1]?.[1]?.[0]
  return address
}

let wired_connectivity_change_callback
export function onWiredConnectivityChange(handler) {
  wired_connectivity_change_callback = handler
}
await wired_device_Properties.subscribe(
  "PropertiesChanged",
  function handler(interface_name, changed_properties) {
    // console.dir(changed_properties, { colors: true, depth: null })
    if (interface_name === "org.freedesktop.NetworkManager.Device") {
      const Ip4Connectivity = changed_properties.find((changed_property) => {
        const [property_name] = changed_property
        return property_name === "Ip4Connectivity"
      })
      if (!Ip4Connectivity) return
      wired_connectivity_change_callback?.()
    }
  },
)

// If the DHCP server goes offline "softly", for example disabling ICS
// NetworkManager won't notice one possible solution is to use connectivity checking and
// await wired_device.subscribe(
//   "StateChanged",
//   function handler(new_state, old_state) {
//     // NM_DEVICE_STATE_ACTIVATED
//     if (new_state !== "ACTIVATED") {
//       wired_connectivity_change_callback?.()
//     }
//   },
// )
// an proably better solution is to open a TCP connection to the host and watch for state changes
