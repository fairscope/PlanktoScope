import { configureDisplay, watch } from "../../lib/scope.js"

watch("display").then(async (messages) => {
  for await (const message of messages) {
    console.log("display", message)
  }
})

const status = `http://planktoscope-sponge-bob`
await configureDisplay({
  status,
})
