/* eslint-disable n/no-top-level-await */

import "observable-polyfill"
import { systemBus } from "dbus.js"
// import { $ } from "execa"
// import { queue } from "./helpers.js"
import { watchProperty } from "./dbus-helpers.js"

const service = systemBus().getService("de.pengutronix.rauc")

const rauc = await service.getInterface("/", "de.pengutronix.rauc.Installer")

export const status = watchProperty(rauc, "Progress")

if (import.meta.main) {
  status.subscribe((value) => console.log(value))
}
