import { setTimeout } from "node:timers/promises"
import { configureDisplay, watch } from "../../lib/scope.js"

watch("display").then(async (messages) => {
  for await (const message of messages) {
    console.log("display", message)
  }
})

function generateRandomString() {
  const length = Math.floor(Math.random() * 11) + 10 // 10–20
  const chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
  let result = ""

  for (let i = 0; i < length; i++) {
    result += chars.charAt(Math.floor(Math.random() * chars.length))
  }

  return result
}

while (true) {
  const status = generateRandomString()
  await configureDisplay({
    status,
  })
  // await setTimeout(1000)
}

// 10:54
