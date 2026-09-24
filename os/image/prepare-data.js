#!/usr/bin/env node

import { $ } from "../../lib/exec.js"
import { deleteAsync } from 'del'

if (import.meta.main) {
  if (process.getuid() !== 0) {
    throw new Error("Please run as root.")
  }

  const path = process.argv[2]
  await prepareData(path)
}

export async function prepareData(p = '/data') {
  await deleteAsync([
    `${p}/**`,
    `!${p}`,
    `!${p}/home`,
    `!${p}/home/pi`,
    `!${p}/tmp`,
    `!${p}/rauc`,
    `!${p}/rauc/**`,
  ], { force: true, dot: true })

  await deleteAsync([
    `${p}/home/pi/**`,
    `!${p}/home/pi/.bashrc`,
  ], { force: true, dot: true })

  await $`sync`
  await $`fstrim --verbose /data`
  await $`sync`
}
