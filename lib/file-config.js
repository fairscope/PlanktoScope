import { rm, writeFile } from "fs/promises"
import { readFile, access, constants, copyFile } from "fs/promises"

const HARDWARE_PATH = "/home/pi/hardware.json"
const SOFTWARE_PATH = "/home/pi/config.json"
const CALIBRATION_PATH = "/home/pi/calibration.json"
const CALIBRATION_DEFAULTS_PATH =
  "/opt/PlanktoScope/default-configs/calibration.json"

async function hasConfig(path) {
  try {
    await access(path, constants.R_OK)
    return true
  } catch {
    return false
  }
}

export async function initConfigFiles(hardware_version) {
  await Promise.all([
    copyFile(
      `/opt/PlanktoScope/default-configs/${hardware_version}.config.json`,
      "/home/pi/config.json",
    ),
    copyFile(
      `/opt/PlanktoScope/default-configs/${hardware_version}.hardware.json`,
      "/home/pi/hardware.json",
    ),
    // Create calibration.json from defaults if it doesn't exist yet.
    // Unlike config/hardware, this never overwrites — preserving user calibrations.
    hasConfig(CALIBRATION_PATH).then(
      (exists) =>
        !exists && copyFile(CALIBRATION_DEFAULTS_PATH, CALIBRATION_PATH),
    ),
  ])
}

async function updateConfig(path, values) {
  const config = await readConfig(path)
  if (!config) {
    throw new Error(`Cannot update missing config ${path}`)
  }

  Object.assign(config, values)

  await writeFile(path, JSON.stringify(config, null, 2))
}

async function readConfig(path) {
  let data

  try {
    data = await readFile(path, { encoding: "utf8" })
  } catch (err) {
    if (err.code === "ENOENT") return null
    throw err
  }

  return JSON.parse(data)
}

export async function removeConfig() {
  await Promise.all([
    rm(HARDWARE_PATH, { force: true }),
    rm(SOFTWARE_PATH, { force: true }),
    rm(CALIBRATION_PATH, { forrce: true }),
  ])
}

export async function hasSoftwareConfig(...args) {
  return hasConfig(SOFTWARE_PATH, ...args)
}

export async function hasHardwareConfig(...args) {
  return hasConfig(HARDWARE_PATH, ...args)
}

export async function updateSoftwareConfig(...args) {
  return updateConfig(SOFTWARE_PATH, ...args)
}

export async function updateHardwareConfig(...args) {
  return updateConfig(HARDWARE_PATH, ...args)
}

export async function readSoftwareConfig(...args) {
  return readConfig(SOFTWARE_PATH, ...args)
}

export async function readHardwareConfig(...args) {
  return readConfig(HARDWARE_PATH, ...args)
}

export async function readCalibrationConfig() {
  return readConfig(CALIBRATION_PATH)
}

export async function updateCalibrationConfig(...args) {
  return updateConfig(CALIBRATION_PATH, ...args)
}

export async function hasCalibrationConfig() {
  return hasConfig(CALIBRATION_PATH)
}
