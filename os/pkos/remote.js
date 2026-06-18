import { readFileSync } from "fs"
import { once } from "events"
import shellEscape from "shell-escape"
import { Client } from "ssh2"

const conn = new Client()

conn.connect({
  host: "192.168.1.45",
  username: "pi",
  privateKey: readFileSync("/home/sonny/.ssh/planktoscope"),
})

await once(conn, "ready")

function exec(cmd) {
  return new Promise((resolve, reject) => {
    const c = shellEscape(cmd)
    console.log(`> ${c}`)
    conn.exec(c, { pty: true }, (err, stream) => {
      if (err) return reject(err)
      stream.pipe(process.stdout)
      stream.stderr.pipe(process.stderr)
      stream.once("close", (code, signal) => {
        if (!code) {
          resolve()
        }
        // console.log(`\nExited with code ${code} and signal ${signal}`)
        else if (code !== 0) {
          reject(new Error(`\nExited with code ${code} and signal ${signal}`))
        } else {
          resolve()
        }
      })
    })
  })
}

async function reboot(slot) {
  await exec(["/opt/PlanktoScope/os/pkos/pkos.js", "reboot", slot])
  // wait
  const result = await exec([
    "sudo",
    "/opt/PlanktoScope/os/pkos/pkos.js",
    "slot",
  ])
  assert.equal(result, slot)
}

// await exec(["sudo", "/opt/PlanktoScope/os/pkos/pkos.js", "slot"])

await reboot("A")

await exec([
  "rauc",
  "install",
  "/data/tmp/PlanktoScopeOS-2026-04-21-raspios.raucb",
])

await reboot("B")

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

await reboot("A")

await exec([
  "sudo",
  "/opt/PlanktoScope/os/pkos/pkos.js",
  "create-bundle",
  "/dev/nvme0n1",
  "B",
  "2026.4.0",
])

await conn.end()
