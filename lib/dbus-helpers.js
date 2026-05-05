import "observable-polyfill"
import { systemBus } from "dbus.js"

export { systemBus }

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

export function normalizeDbus(value) {
  if (!Array.isArray(value)) return value

  // Typed wrapper: [[{type}], [value]]
  if (
    value.length === 2 &&
    Array.isArray(value[0]) &&
    Array.isArray(value[1]) &&
    value[0][0] &&
    typeof value[0][0].type === "string"
  ) {
    const typeInfo = value[0][0]
    const type = typeInfo.type
    const inner = value[1][0]

    switch (type) {
      case "v": // variant
        return normalizeDbus(inner)

      case "a": {
        // array
        const child = typeInfo.child && typeInfo.child[0]

        // Detect dictionary a{...}
        if (child && child.type === "{") {
          const obj = {}
          for (const entry of inner) {
            const [k, v] = normalizeDbus(entry)
            obj[k] = v
          }
          return obj
        }

        // Regular array
        return inner.map(normalizeDbus)
      }

      case "{": {
        // dict entry
        const [k, v] = inner
        return [normalizeDbus(k), normalizeDbus(v)]
      }

      case "(": // struct
        return inner.map(normalizeDbus)

      // Scalars
      case "s":
      case "o":
      case "g":
      case "b":
      case "y":
      case "n":
      case "q":
      case "i":
      case "u":
      case "x":
      case "t":
      case "d":
        return inner

      default:
        return normalizeDbus(inner)
    }
  }

  // Fallback recursion
  return value.map(normalizeDbus)
}
