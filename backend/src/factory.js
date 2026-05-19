// This file is related to factory setup of the PlanktoScope
// factory setup refers to configuration done at runtime or by FairScope
// without involvment of the users
// For example updating the EEPROM

import crypto from "node:crypto"
// import * as z from "zod"

import { read, write } from "../../lib/eeprom.js"
import { procedure, request } from "../../lib/mqtt.js"
import { setHardwareVersion } from "../../lib/hardware.js"

await procedure("factory/init", async () => {
  let eeprom = await read()

  if (eeprom?.custom_data?.eeprom_version !== 0) {
    eeprom = {
      product_uuid: crypto.randomUUID(),
      product_id: "",
      product_ver: "",
      vendor: "FairScope",
      product: "PlanktoScope HAT v3",
      current_supply: 0,
      dt_blob: "planktoscope-hat-v3",
      custom_data: {
        serial_number: "",
        hardware_version: "v3.0",
        eeprom_version: 0,
        led_operating_time: 0,
      },
    }
  }

  // PS in hexadecimal
  eeprom.product_id = "0x5053"
  // first revision of the PlanktoScope HAT 0x5053
  eeprom.product_ver = "0x0001"

  return eeprom
})

await procedure("factory/update", async (data) => {
  const { hardware_version } = data.custom_data

  await Promise.all([
    hardware_version && write(data),
    setHardwareVersion(hardware_version),
  ])

  if (hardware_version === "v3.0") {
    await request("light", { action: "off" })
    await request("light", { action: "save" })

    await request("actuator/bubbler", { action: "off" })
    await request("actuator/bubbler", { action: "save" })
  }
})
