import {
  pump,
  stopPump,
  getPumpConfiguration,
  setPumpConfiguration,
  watch,
} from "../../lib/scope.js"

watch("status/pump").then(async (messages) => {
  for await (const message of messages) {
    console.log("pump", message)
  }
})

let config
config = await getPumpConfiguration()
console.log({ config })
await setPumpConfiguration(config)
config = await getPumpConfiguration()
console.log({ config })

setTimeout(() => {
  stopPump().catch(console.error)
}, 1000)

await pump({ direction: "BACKWARD", flowrate: 10, volume: 1 })
