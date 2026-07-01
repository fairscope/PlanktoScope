import shellEscape from "shell-escape"
import { PassThrough } from "stream"
import fs from "fs"
import ora from "ora"

import { Client } from "ssh2"

export function waitForSSH(config, interval = 5000, maxTries = 120) {
  let tries = 0
  let success = false

  return new Promise((resolve, reject) => {
    const attempt = () => {
      let timeout = null

      const conn = new Client()

      function onReady() {
        success = true
        resolve(conn)
        cleanup()
      }

      function onError(err) {
        // console.log("onError", err)
        conn.destroy()
        if (success) return
        if (timeout) return
        tries++
        if (tries >= maxTries) return reject(new Error("SSH not reachable"))
        timeout = setTimeout(attempt, interval)
      }

      function cleanup() {
        conn.removeListener("ready", onReady)
        conn.removeListener("error", onError)
      }

      conn.on("ready", onReady)
      conn.on("error", onError)
      conn.connect(config)
    }

    attempt()
  })
}

export function exec(conn, cmd) {
  return new Promise((resolve, reject) => {
    const c = shellEscape(cmd)
    console.log(`> ${c}`)
    conn.exec(c, { pty: false }, (err, stream) => {
      if (err) return reject(err)

      let stdout = ""
      const tee = new PassThrough()
      tee.on("data", (chunk) => {
        stdout += chunk.toString()
      })

      stream.pipe(tee).pipe(process.stdout)
      stream.stderr.pipe(process.stderr)
      stream.once("close", (code, signal) => {
        if (!code) {
          resolve({ stdout })
        }
        // console.log(`\nExited with code ${code} and signal ${signal}`)
        else if (code !== 0) {
          reject(new Error(`\nExited with code ${code} and signal ${signal}`))
        } else {
          resolve({ stdout })
        }
      })
    })
  })
}

function _sftp(conn) {
  return new Promise((resolve, reject) => {
    conn.sftp((err, sftp) => {
      if (err) return reject(err)
      resolve(sftp)
    })
  })
}

export function getFileSize(sftp, path) {
  return new Promise((resolve, reject) => {
    sftp.stat(path, (err, stats) => {
      if (err) return reject(err)
      resolve(stats.size)
    })
  })
}

export function downloadFile(conn, remote, local) {
  return new Promise(async (resolve, reject) => {
    const spinner = ora().start()

    let downloaded = 0

    const sftp = await _sftp(conn)

    const size = await getFileSize(sftp, remote)

    const rs = sftp.createReadStream(remote)
    const ws = fs.createWriteStream(local)

    rs.on("data", (chunk) => {
      downloaded += chunk.length
      const percent = ((downloaded / size) * 100).toFixed(1)
      spinner.text = `Downloading ${percent}%`
    })

    rs.pipe(ws)

    rs.on("error", reject)
    ws.on("error", reject)
    ws.on("close", () => {
      spinner.succeed()
      resolve()
    })
  })
}
