import multer from "multer"

import app from "./app.js"
import { status } from "../../lib/rauc.js"

const uploads = multer({
  dest: "/home/pi/data/uploads",
})
app.post("/api/update", uploads.single("bundle"), (req, res) => {
  console.log(req.file)
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

status.subscribe((progress) => {
  broadcast(progress)
})
