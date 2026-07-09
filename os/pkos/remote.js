#!/usr/bin/env node

import assert from "assert"
import { readFileSync } from "fs"
import { once } from "events"
import os from "os"
import { parseArgs } from "node:util"
import { oraPromise } from "ora"

import { waitForSSH, exec, downloadFile } from "./ssh.js"
import { join } from "path"
import { basename } from "node:path"
import { setTimeout } from "node:timers/promises"

let conn
const config = {
  username: "pi",
}

const PARTNS = {
  A: "2",
  B: "3",
}

const SLOTS = Object.fromEntries(
  Object.entries(PARTNS).map(([key, value]) => [value, key]),
)

// Kinda duplicate from rpi.js
async function getBootedPartitionNumber() {
  const { stdout } = await exec(conn, [
    "sudo",
    "fdtget",
    "/sys/firmware/fdt",
    "/chosen/bootloader",
    "partition",
  ])
  const n = Number(stdout.trim())
  if (!Number.isInteger(n)) throw new Error("Could not get booted partition")
  return n
}

async function getBootedSlot() {
  const booted_partn = await getBootedPartitionNumber()
  return SLOTS[booted_partn]
}

async function useSlot(bootname) {
  if ((await getBootedSlot()) === bootname) {
    return
  }

  function log(err) {
    console.error(err)
  }

  // ignore error triggered by reboot
  conn.on("error", log)
  process.on("uncaughtException", log)

  const p1 = once(conn, "close")
  const p2 = exec(conn, ["sudo", "reboot", PARTNS[bootname]])
  await Promise.all([p1, p2])
  conn.end()

  process.removeListener("uncaughtException", log)

  conn = await oraPromise(waitForSSH(config), {
    text: "SSH waiting for connection",
    successText: "SSH reconnected",
    failText: "SSH timeout",
  })

  assert.equal(await getBootedSlot(), bootname)
}

const { values } = parseArgs({
  options: {
    host: {
      type: "string",
    },
    key: {
      type: "string",
      default: join(os.homedir(), ".ssh/planktoscope"),
    },
    bootname: {
      type: "string",
    },
    version: {
      type: "string",
    },
  },
})

const { host, key, bootname, version } = values
if (!host || !key || !bootname || !version) {
  throw new Error(
    `Usage: remote.js --host=192.168.x.x [--key=~/.ssh/key] --bootname=B --version=202x.x.x`,
  )
}

Object.assign(config, {
  host,
  privateKey: readFileSync(key),
})

conn = await waitForSSH(config)

const other = bootname === "A" ? "B" : "A"

// await useSlot(other)

// await exec(conn, [
//   "sudo",
//   "NODE_DEBUG=execa",
//   "node",
//   "/opt/PlanktoScope/os/pkos/pkos.js",
//   "install-rpios",
//   "/dev/nvme0n1",
//   bootname,
// ])

await useSlot(bootname)

await useSlot(other)

// await exec(conn, ["sudo", "apt", "update", "-y"])
// await exec(conn, ["sudo", "apt", "install", "-y", "git", "just"])
// await exec(conn, [
//   "git",
//   "clone",
//   "--branch",
//   "remote",
//   // "--no-progress",
//   "https://github.com/fairscope/PlanktoScope.git",
//   "/home/pi/repo",
// ])
// await exec(conn, ["sudo", "mv", "/home/pi/repo", "/opt/PlanktoScope"])
// await exec(conn, ["sudo", "chown", "-R", "pi:pi", "/opt/PlanktoScope"])
// await exec(conn, [
//   "just",
//   "--justfile",
//   "/opt/PlanktoScope/justfile",
//   "install-node",
// ])
// await exec(conn, ["just", "--justfile", "/opt/PlanktoScope/lib/justfile"])
// await exec(conn, ["just", "--justfile", "/opt/PlanktoScope/os/pkos/justfile"])
// await exec(conn, ["/opt/PlanktoScope/os/pkos/pkos.js", "prepare"])

// await useSlot(other)

// const { stdout } = await exec(conn, [
//   "sudo",
//   "/opt/PlanktoScope/os/pkos/pkos.js",
//   "create-bundle",
//   "/dev/nvme0n1",
//   bootname,
//   version,
// ])

// const bundle_path = stdout.trim()
// const filename = basename(bundle_path)

// await downloadFile(conn, bundle_path, filename)

conn.end()
