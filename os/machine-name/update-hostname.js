#!/usr/bin/env node

import { readFile } from "node:fs/promises"
import { updateName } from "../../lib/identity.js"

if (import.meta.main) {
  if (process.getuid() !== 0) {
    throw new Error("Please run as root.")
  }

  const name = await readFile("/run/machine-name", "utf8")
  await updateName(name)
  process.exit(0)
}
