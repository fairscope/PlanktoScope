import { setTimeout } from "node:timers/promises"
import { configureDisplay, watch } from "../../lib/scope.js"

watch("display").then(async (messages) => {
  for await (const message of messages) {
    console.log("display", message)
  }
})

let n = 0

while (true) {
  const status = `http://192.168.1.${n++}`
  await configureDisplay({
    status,
  })
  await setTimeout(1000)
}
