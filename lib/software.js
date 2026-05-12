import { $ } from "execa"
import git from "isomorphic-git"
import fs from "fs"

import { cache } from "./helpers.js"
import { normalizeDbus, readProperty, systemBus } from "./dbus-helpers.js"

const getRoot = cache(() => git.findRoot({ fs, filepath: import.meta.dirname }))

async function getBootedSlotBundleVersion() {
  const slots = await getSlotStatus()
  return (
    Object.values(slots).find((slot) => slot.state === "booted")?.[
      "bundle.version"
    ] || null
  )
}

export async function getSoftwareVersion() {
  try {
    return await getBootedSlotBundleVersion()
  } catch {}

  try {
    return `git ${(await getCommit()).slice(0, 7)}`
  } catch {}

  return "unknown"
}

async function getUrl() {
  const dir = await getRoot()

  const [remotes, branch] = await Promise.all([
    git.listRemotes({ fs, dir }),
    git.currentBranch({
      fs,
      dir,
      test: true,
    }),
  ])
  if (!branch) return remotes[0]?.url

  const remote = await git.getConfig({
    fs,
    dir,
    path: `branch.${branch}.remote`,
  })
  if (!remote) return remotes[0]?.url

  return remotes.find((item) => item.remote === remote)?.url
}

async function getCommit() {
  const full_sha = await git.resolveRef({
    fs,
    dir: await getRoot(),
    ref: "HEAD",
  })
  return full_sha
}

export async function getSoftwareVersioning() {
  const [commit, url, version] = await Promise.all([
    getCommit(),
    getUrl(),
    getSoftwareVersion(),
  ])

  return {
    repo: url,
    commit,
    version,
  }
}

export const getInstaller = cache(() => {
  const service = systemBus().getService("de.pengutronix.rauc")
  return service.getInterface("/", "de.pengutronix.rauc.Installer")
})

// https://rauc.readthedocs.io/en/latest/reference.html#installbundle-method
export async function triggerInstall(path) {
  const installer = await getInstaller()
  if (!installer) {
    throw new Error("Installer not available")
  }
  await installer.InstallBundle(path, [])
  const current_operation = await readProperty(installer, "Operation")
  if (current_operation !== "installing")
    throw new Error(`Current rauc operation is "${current_operation}".`)
}

// https://rauc.readthedocs.io/en/latest/reference.html#inspectbundle-method
export async function getBundleInfo(uri) {
  const installer = await getInstaller()
  if (!installer) {
    throw new Error("Installer not available")
  }
  const raw = await installer.InspectBundle(uri, [])
  const normalized = normalizeDbus(raw)
  const dictEntries = normalized[0]
  const result = Object.fromEntries(dictEntries)

  const { version, compatible, build } = result.update

  return {
    version,
    build,
    compatible,
    uri,
  }
}

// At the time of writing rauc poller is not ready yet
// but this should be easy to replace with it once it is
// const url = "http://localhost/api/files/PlanktoScopeOS.raucb"
const url = "https://backend.eplankton.org/api/planktoscope-update"
export async function checkForUpdate() {
  let value = null

  const installer = await getInstaller()
  if (!installer) return value

  try {
    const [bundle_info, compatible] = await Promise.all([
      getBundleInfo(url),
      readProperty(installer, "Compatible"),
    ])
    if (bundle_info.compatible !== compatible) return value
    value = bundle_info
  } catch (err) {
    console.error(err)
  }

  return value
}

async function getSlotStatus() {
  const installer = await getInstaller()
  if (!installer) {
    throw new Error("Installer not available")
  }
  const raw = await installer.GetSlotStatus()
  const normalized = normalizeDbus(raw)
  const dictEntries = normalized[0]

  const slots = Object.fromEntries(dictEntries)
  for (const slot in slots) {
    slots[slot] = Object.fromEntries(slots[slot])
  }

  return slots
}
