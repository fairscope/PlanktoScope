import assert from "assert"
import { readFileSync } from "fs"
import shellEscape from "shell-escape"
import { PassThrough } from "stream"
import { once } from "events"

import { waitForSSH } from "./waitForSSH.js"
import { setTimeout } from "timers/promises"

let conn

function exec(cmd) {
  return new Promise((resolve, reject) => {
    const c = shellEscape(cmd)
    console.log(`> ${c}`)
    conn.exec(c, { pty: true }, (err, stream) => {
      if (err) return reject(err)

      let output = ""
      const tee = new PassThrough()
      tee.on("data", (chunk) => {
        output += chunk.toString()
      })

      stream.pipe(tee).pipe(process.stdout)
      stream.stderr.pipe(process.stderr)
      stream.once("close", (code, signal) => {
        if (!code) {
          resolve(output)
        }
        // console.log(`\nExited with code ${code} and signal ${signal}`)
        else if (code !== 0) {
          reject(new Error(`\nExited with code ${code} and signal ${signal}`))
        } else {
          resolve(output)
        }
      })
    })
  })
}

async function reboot(slot) {
  // ignore error triggered by reboot
  conn.on("error", () => {})

  const p1 = once(conn, "close")
  const p2 = exec(["sudo", "/opt/PlanktoScope/os/pkos/pkos.js", "reboot", slot])
  // const p2 = exec(["sudo", "reboot", "3"])
  await Promise.all([p1, p2])

  conn = await waitForSSH({
    // host: "192.168.1.45",
    host: "10.42.0.94",
    username: "pi",
    privateKey: readFileSync("/home/sonny/.ssh/planktoscope"),
  })

  // const result = await exec([
  //   "sudo",
  //   "/opt/PlanktoScope/os/pkos/pkos.js",
  //   "slot",
  // ])
  // assert.equal(result.trim(), slot)
}

conn = await waitForSSH({
  // host: "192.168.1.45",
  host: "10.42.0.94",
  username: "pi",
  privateKey: readFileSync("/home/sonny/.ssh/planktoscope"),
})

const slot = await exec(["sudo", "/opt/PlanktoScope/os/pkos/pkos.js", "slot"])
if (slot.trim() !== "B") {
  await reboot("B")
}

// await exec(["uptime"])
// process.exit()

await exec([
  "sudo",
  "NODE_DEBUG=execa",
  "node",
  "/opt/PlanktoScope/os/pkos/pkos.js",
  "install-rpios",
  "/dev/nvme0n1",
  "A",
])
// await exec([
//   "rauc",
//   "install",
//   "/data/tmp/PlanktoScopeOS-2026-04-21-raspios.raucb",
// ])

await reboot("A")

await exec(["sudo", "apt", "update", "-y"])
await exec(["sudo", "apt", "install", "-y", "git", "just"])
await exec([
  "git",
  "clone",
  "https://github.com/fairscope/PlanktoScope.git",
  "/home/pi/repo",
])
await exec(["sudo", "mv", "/home/pi/repo", "/opt/PlanktoScope"])
await exec(["sudo", "chown", "-R", "pi:pi", "/opt/PlanktoScope"])
await exec(["just", "--justfile", "/opt/PlanktoScope/os/pkos/justfile"])
await exec(["/opt/PlanktoScope/os/pkos/pkos.js", "prepare"])

await reboot("B")

await exec([
  "sudo",
  "/opt/PlanktoScope/os/pkos/pkos.js",
  "create-bundle",
  "/dev/nvme0n1",
  "A",
  "2026.4.0",
])

conn.end()
