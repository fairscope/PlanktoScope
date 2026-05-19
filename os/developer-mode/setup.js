#!/usr/bin/env node

import { access } from "node:fs/promises"
import { $ } from "execa"

const REPO_URL = "git@github.com:fairscope/PlanktoScope.git"

const previous_cwd = process.cwd()

process.chdir("/opt/PlanktoScope")

if (await isGitRepo()) {
  await $`git remote set-url origin ${REPO_URL}`
  await $`git config remote.origin.fetch "+refs/heads/*:refs/remotes/origin/*"`
  await $`git fetch origin`
} else {
  await $`git clone --bare ${REPO_URL} .git`
  await $`git config --local --bool core.bare false`
  await $`git reset HEAD -- .`
}

await $`rm -f gitinfo.json`

await $`git config core.hooksPath dev/hooks`

process.chdir(previous_cwd)

async function isGitRepo() {
  try {
    await access(".git")
    return true
  } catch {
    return false
  }
}
