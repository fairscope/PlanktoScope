import * as z from "zod"

import { publish } from "./mqtt.js"
import {
  getWifiRegulatoryDomains,
  setWifiRegulatoryDomain,
  getWifiRegulatoryDomain,
} from "./country.js"
import { getTimezones, getTimezone, setTimezone } from "./timezone.js"

import { updateSoftwareConfig } from "./file-config.js"

export async function readSetup() {
  const [regions, region, timezones, timezone] = await Promise.all([
    getWifiRegulatoryDomains(),
    getWifiRegulatoryDomain(),
    getTimezones(),
    getTimezone(),
  ])

  return {
    regions,
    region,
    timezones,
    timezone,
  }
}

const Schema = z.object({
  region: z.string(),
  timezone: z.string(),
})

export async function writeSetup(data) {
  const { region, timezone } = Schema.parse(data)

  await Promise.all([setWifiRegulatoryDomain(region), setTimezone(timezone)])
  await updateSoftwareConfig({ user_setup: true })

  await publish("setup/ready", {})
}
