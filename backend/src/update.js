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

  if (data.action == "reboot") {
    setTimeout(() => {
      reboot().catch(console.error)
    }, 1000)
    return
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
