import { rm } from "node:fs/promises"
import { readRaucSystemConf } from "../../os/rauc/rauc.js"

import express from "express"
import multer from "multer"
import {
  normalizeDbus,
  readProperty,
  systemBus,
} from "../../lib/dbus-helpers.js"

import app from "./app.js"
import { watchProperty } from "../../lib/dbus-helpers.js"

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

// Keep track of clients
const clients = new Set()
app.get("/api/update/events", (req, res) => {
  // Required SSE headers
  res.setHeader("Content-Type", "text/event-stream")
  res.setHeader("Cache-Control", "no-cache")
  res.setHeader("Connection", "keep-alive")

  // Send initial comment to establish connection in some proxies
  res.flushHeaders?.()

  const client = {
    id: Date.now(),
    res,
  }
  clients.add(client)

  req.on("close", () => {
    clients.delete(client)
  })
})

function broadcast(data) {
  clients.forEach((client) => {
    client.res.write(`data: ${JSON.stringify(data)}\n\n`)
  })
}

const service = systemBus().getService("de.pengutronix.rauc")
const rauc = await service.getInterface("/", "de.pengutronix.rauc.Installer")

watchProperty(rauc, "Progress").subscribe((progress) => {
  console.log(progress)
  broadcast(progress)
})

// https://rauc.readthedocs.io/en/latest/reference.html#installbundle-method
async function triggerInstall(path) {
  await rauc.InstallBundle(path, [])
  const current_operation = await readProperty(rauc, "Operation")
  console.log({ current_operation })
  if (current_operation !== "installing")
    throw new Error(`Current rauc operation is "${current_operation}".`)
}

// https://rauc.readthedocs.io/en/latest/reference.html#inspectbundle-method
async function getBundleInfo(path) {
  const raw = await rauc.InspectBundle(path, [])
  const normalized = normalizeDbus(raw)
  const dictEntries = normalized[0]
  const result = Object.fromEntries(dictEntries)

  const { version, compatible, build } = result.update

  return {
    version,
    build,
    compatible,
    path,
  }
}

if (import.meta.main) {
  // await triggerInstall("/data/tmp/fpp")
  await getBundleInfo("/data/tmp/e5464c1b6a138ca358e9683cbe5d73f8")
}
