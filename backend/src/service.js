#!/usr/bin/env node

import path from "node:path"

import { readSoftwareConfig, removeConfig } from "../../lib/file-config.js"
import { capture } from "../../lib/scope.js"

import app from "./app.js"

import "./factory.js"
// import "./config.js"
import "./led-operating-time.js"
import "./network.js"
import "./update.js"

process.title = "planktoscope-org.backend"

app.post("/api/capture", async (req, res) => {
  const result = await capture({ jpeg: true })

  const relative_path = path.relative("/home/pi/data", result.jpeg)

  const url = new URL(req.headers.origin)
  url.port = 80
  url.pathname = path.join("/api/files/", relative_path)

  res.json({ url_jpeg: url })
})

app.post("/api/reset", async (req, res) => {
  await removeConfig()
  res.status(200)
  res.end()
})

app.get("/", async (req, res) => {
  const software_config = await readSoftwareConfig()

  if (software_config?.user_setup !== true) {
    return res.redirect(302, "/ps/node-red-v2/dashboard/setup")
  }

  return res.redirect(302, "/ps/node-red-v2/dashboard")
})

app.listen(4000)
