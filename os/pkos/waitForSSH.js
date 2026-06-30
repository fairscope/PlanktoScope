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
