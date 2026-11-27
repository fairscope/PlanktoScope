import {
  readCalibrationConfig,
  updateCalibrationConfig,
  updateHardwareConfig,
} from "../../lib/file-config.js"
import { publish, procedure } from "../../lib/mqtt.js"

function toIntensity(value) {
  const intensity = Number(value)

  if (!Number.isFinite(intensity) || intensity < 0 || intensity > 1) {
    throw new Error(`Invalid LED intensity: ${JSON.stringify(value)}`)
  }

  return intensity
}

function toWhiteBalance(value) {
  const red = Number(value?.red)
  const blue = Number(value?.blue)

  if (!Number.isFinite(red) || red <= 0 || !Number.isFinite(blue) || blue <= 0) {
    throw new Error(`Invalid white balance gains: ${JSON.stringify(value)}`)
  }

  return { red, blue }
}

async function publishCalibration() {
  const calibration = (await readCalibrationConfig()) || {}

  await publish("status/calibration", calibration, null, { retain: true })
}

async function applyWhiteBalance({ red, blue }) {
  await updateHardwareConfig({ red_gain: red, blue_gain: blue })

  await publish("imager/image", {
    action: "settings",
    settings: { white_balance_gain: { red: red * 100, blue: blue * 100 } },
  })
}

await procedure("calibration/read", async () => {
  return (await readCalibrationConfig()) || {}
})

await procedure("calibration/save", async (data) => {
  const updates = {}

  if (data?.led_intensity !== undefined) {
    updates.led_intensity = toIntensity(data.led_intensity)
  }

  if (data?.white_balance !== undefined) {
    updates.white_balance = toWhiteBalance(data.white_balance)
  }

  if (Object.keys(updates).length === 0) {
    throw new Error("No calibration values to save")
  }

  await updateCalibrationConfig(updates)

  if (updates.white_balance) {
    await applyWhiteBalance(updates.white_balance)
  }

  await publishCalibration()

  return updates
})

const calibration = (await readCalibrationConfig()) || {}

if (calibration.white_balance) {
  try {
    await applyWhiteBalance(toWhiteBalance(calibration.white_balance))
  } catch (err) {
    console.error(err)
  }
}

await publishCalibration()
