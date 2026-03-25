#!/usr/bin/env node

import assert from "node:assert"
import { umount } from "./lib.js"

if (import.meta.main) {
  const [, , device] = process.argv
  assert.ok(device)

  await umount(device)
}
