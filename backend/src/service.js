#!/usr/bin/env node

import path from "node:path"

import express from "express"
import cors from "cors"

import "./factory.js"
// import "./config.js"
import "./led-operating-time.js"
import "./network.js"
import { readSoftwareConfig, removeConfig } from "../../lib/file-config.js"
import { capture } from "../../lib/scope.js"

process.title = "planktoscope-org.backend"

const app = express()
app.use(cors())

app.post("/api/capture", async (req, res) => {
  const result = await capture({ jpeg: true })

  const relative_path = path.relative("/home/pi/data", result.jpeg)

  const url = new URL(req.headers.origin)
  url.port = 80
  url.pathname = path.join("/api/files/", relative_path)

  res.json({ url_jpeg: url })
})

app.use("/api/files", express.static("/home/pi/data"))

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

const path_spa = "/home/pi/PlanktoScope/frontend/dist"
app.use("/", express.static(path_spa))
app.get("/{*splat}", (req, res) => {
  res.sendFile(path.join(path_spa, "index.html"))
})

app.listen(4000)
