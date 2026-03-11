export async function readProperty(iface, propName) {
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

export function observeProperties(iface) {
  return new Observable(async (subscriber) => {
    iface = await iface.$parent.service.getInterface(
      iface.$parent.name,
      "org.freedesktop.DBus.Properties",
    )
    iface.subscribe(
      "PropertiesChanged",
      async function handler(interface_name, changed_properties) {
        for (const [property_name, [, values]] of changed_properties) {
          subscriber.next({
            name: property_name,
            value: values[0],
          })
        }
      },
    )
  })
}

export function watchProperty(iface, propName) {
  return new Observable(async (subscriber) => {
    await Promise.all([
      readProperty(iface, propName).then((val) => subscriber.next(val)),
      (async function () {
        iface = await iface.$parent.service.getInterface(
          iface.$parent.name,
          "org.freedesktop.DBus.Properties",
        )
        iface.subscribe(
          "PropertiesChanged",
          async function handler(interface_name, changed_properties) {
            const prop = changed_properties.find((changed_property) => {
              const [property_name] = changed_property
              return property_name === propName
            })
            if (!prop) return
            const [, [, values]] = prop
            subscriber.next(values[0])
          },
        )
      })(),
    ])
  })
}
