/* eslint-disable n/no-top-level-await */

import { systemBus } from "dbus.js"
import { readProperty } from "../dbus-helpers.js"

// Work in progress for https://github.com/fairscope/PlanktoScope/issues/886

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
          readProperty(access_point, propName),
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
