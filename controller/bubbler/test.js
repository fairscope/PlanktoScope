import { startBubbler, stopBubbler, watch } from "../../lib/scope.js"
import { setTimeout } from "node:timers/promises"

watch("status/bubbler").then(async (messages) => {
  for await (const message of messages) {
    console.log("bubbler", message)
  }
})

await stopBubbler()

for (const value of [0.25, 0.5, 0.75, 100]) {
  await startBubbler({ value })
  await setTimeout(2000)
}

await stopBubbler()
