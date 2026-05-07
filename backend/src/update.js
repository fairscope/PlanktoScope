import multer from "multer"
import { readProperty } from "../../lib/dbus-helpers.js"
import { reboot } from "../../lib/hardware.js"

import app from "./app.js"
import { watchProperty } from "../../lib/dbus-helpers.js"
import {
  getInstaller,
  getBundleInfo,
  triggerInstall,
  checkForUpdate,
} from "../../lib/software.js"
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
// const signals = ["Completed"]

async function getStatus() {
  const installer = await getInstaller()
  const values = await Promise.all(
    props.map((prop) => readProperty(installer, prop)),
  )
  const obj = Object.fromEntries(props.map((key, i) => [key, values[i]]))
  return obj
}

async function publishStatus() {
  const status = await getStatus()
  await publish("software-updater/status", status, null, {
    retain: true,
  })
}

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
  await publish(
    "software-updater/update-available",
    [!!bundle_info, bundle_info],
    null,
    {
      retain: true,
    },
  )
}

;(async () => {
  const installer = await getInstaller()
  if (!installer) return console.log("Installer not available")

  await publishStatus()

  props.forEach((prop) => {
    watchProperty(installer, prop).subscribe(() => publishStatus())
  })
})()

if (import.meta.main) {
  console.log(await getStatus())
  // const bundle_info = await getBundleInfo(url)
  // console.log(bundle_info)
}
