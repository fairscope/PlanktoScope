import { Temporal } from "@js-temporal/polyfill"

import { getHardwareVersion } from "../../lib/hardware.js"
import { getSoftwareVersioning } from "../../lib/software.js"
import { getMachineName } from "../../lib/identity.js"
import {
  acquire,
  configure,
  FORWARD,
  turnLightOff,
  turnLightOn,
  watch,
} from "../../lib/scope.js"
import { setTimeout } from "node:timers/promises"

watch("status/imager").then(async (messages) => {
  for await (const message of messages) {
    console.log("imager", message)
  }
})

const hardware_version = await getHardwareVersion()
const machine_name = await getMachineName()
const software = await getSoftwareVersioning()

const t = Temporal.Now.plainDateTimeISO("UTC")
const datetime = t.toString().split(".")[0]
const date = Temporal.PlainDate.from(t).toString()
const time = Temporal.PlainTime.from(t).toString()
const acquisition_id = `acquisition_${datetime}`
const sample_id = `sample_${datetime}`

const config = {
  project: "test",
  operator: "pi",
  sampling_gear: "PlanktoScope-test",
  number_of_images: 10,
  flowcell_volume: 2.08, // μL
}

const metadata_sample = {
  sample_project: config.project,
  sample_id,
  sample_operator: config.operator,
  sample_sampling_gear: config.sampling_gear,
  acq_id: acquisition_id,
  acq_instrument: `PlanktoScope ${hardware_version}`,
  acq_instrument_id: machine_name,
  acq_celltype: 300,
  acq_minimum_mesh: 20,
  acq_maximum_mesh: 300,
  acq_volume: (config.number_of_images * config.flowcell_volume) / 1000, // μL to mL
  acq_magnification: "1.2",
  acq_fnumber_objective: 12,
  acq_nb_frame: config.number_of_images,
  acq_software: `PlanktoScope OS ${software.version}`,
  object_date: date,
  object_time: time,
  object_lat: undefined,
  object_lon: undefined,
  object_depth_min: 0,
  object_depth_max: 0,
  process_pixel: 0.75,
  process_source: software.repo,
  process_commit: software.commit,
  acq_camera_resolution: "4056x3040",
  acq_camera_iso: 150,
  acq_camera_shutter_speed: 125,
  // FIXME: for some reason ecotaxa uses acq_instrument_id as acq_uuid and sample_uuid
  acq_uuid: crypto.randomUUID(),
  sample_uuid: crypto.randomUUID(),
}

;(async () => {
  await configure(metadata_sample)

  await turnLightOn()
  await setTimeout(1)

  let acquisition_path
  try {
    const { path } = await acquire({
      pump_direction: FORWARD,
      volume: 0.01, // Volume to pump between 2 images!
      nb_frame: 10,
      sleep: 0.1,
    })
    acquisition_path = path
  } finally {
    await turnLightOff()
  }

  console.log(acquisition_path)
})()
