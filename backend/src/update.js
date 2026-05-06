import { rm } from "node:fs/promises"
import { readRaucSystemConf } from "../../os/rauc/rauc.js"

import express from "express"
import multer from "multer"
import {
  normalizeDbus,
  readProperty,
  systemBus,
} from "../../lib/dbus-helpers.js"
import { reboot } from "../../lib/hardware.js"

import app from "./app.js"
import { watchProperty } from "../../lib/dbus-helpers.js"
import { installer, getBundleInfo, triggerInstall } from "../../lib/software.js"
import { procedure, publish } from "../../lib/mqtt.js"

const uploads = multer({
  dest: "/data/tmp",
})
app.post("/api/update/upload", uploads.single("bundle"), async (req, res) => {
  const info = await getBundleInfo(req.file.path)
  res.status(200)
  res.json(info)
})

app.post("/api/update/install", express.json(), async (req, res) => {
  const { path } = req.body
  if (!path) {
    res.status(404)
    res.end()
    return
  }

  await triggerInstall(path)

  res.status(200)
  res.end()
})

app.post("/api/update/reboot", async (req, res) => {
  res.status(201)
  res.end()

  setTimeout(() => {
    reboot().catch(console.error)
  }, 1000)
})

const props = [
  "Operation",
  "LastError",
  "Progress",
  /* "Compatible", "Variant", */
]
const signals = ["Completed"]

async function getStatus() {
  const values = await Promise.all(
    props.map((prop) => readProperty(installer, prop)),
  )
  const obj = Object.fromEntries(props.map((key, i) => [key, values[i]]))
  return obj
}

// // Keep track of clients
// const clients = new Set()
// app.get("/api/update/events", (req, res) => {
//   // Required SSE headers
//   res.setHeader("Content-Type", "text/event-stream")
//   res.setHeader("Cache-Control", "no-cache")
//   res.setHeader("Connection", "keep-alive")

//   // Send initial comment to establish connection in some proxies
//   res.flushHeaders?.()

//   const client = {
//     id: Date.now(),
//     res,
//   }
//   clients.add(client)

//   getStatus()
//     .then((data) => {
//       client.res.write(`data: ${JSON.stringify(data)}\n\n`)
//     })
//     .catch(console.error)

//   req.on("close", () => {
//     clients.delete(client)
//   })
// })

// function broadcast(data) {
//   clients.forEach((client) => {
//     client.res.write(`data: ${JSON.stringify(data)}\n\n`)
//   })
// }

async function publishStatus() {
  const status = await getStatus()
  // broadcast(status)
  await publish("status/software-updater", status, null, {
    retain: true,
  })
}

props.forEach((prop) => {
  watchProperty(installer, prop).subscribe(() => publishStatus())
})

await publishStatus()

await procedure("software-updater", async (data) => {
  if (data.action == "poll") {
    await poll()
    return
  }

  if (data.action == "install") {
    await triggerInstall(data.uri)
    return
  }

  if (data.action == "info") {
    return getBundleInfo(data.uri)
  }
})

async function poll() {
  const bundle_info = await checkForUpdate()
  await publish("status/software-updater/update-available", bundle_info, null, {
    retain: true,
  })
}

if (import.meta.main) {
  console.log(await getStatus())
  const bundle_info = await getBundleInfo(url)
  console.log(bundle_info)
}
