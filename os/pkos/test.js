import { waitForSSH } from "./ssh.js"
import { readFileSync } from "fs"

let conn
const config = {
  username: "pi",
}

Object.assign(config, {
  host: "192.168.1.22",
  privateKey: readFileSync("/home/sonny/.ssh/planktoscope"),
})

conn = await waitForSSH(config)

console.log("ok")
