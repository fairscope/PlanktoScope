import { $ } from "./exec.js"

import { updateSoftwareConfig } from "./file-config.js"

export async function getTimezones() {
  const { stdout } = await $`timedatectl list-timezones --no-pager`

  const timezones = []

  for (const tz of stdout.split("\n")) {
    if (!tz) continue

    // https://blacksheepcode.com/posts/til_etc_timezone_is_backward
    if (tz.startsWith("Etc/")) continue

    // Some (all?) timezones without a region do not work with set-timezone
    // sudo timedatectl set-timezone Zulu
    // Failed to set time zone: Invalid or not installed time zone 'Zulu'
    // same with Israel, Iran, ...
    // https://github.com/fairscope/PlanktoScope3/issues/357
    if (tz !== "UTC" && !tz.includes("/")) continue

    timezones.push({ value: tz, label: tz })
  }

  return timezones
}

export async function setTimezone(timezone) {
  await $`sudo timedatectl set-timezone ${timezone}`
  // save configuration
  await updateSoftwareConfig({ timezone })
}

export async function getTimezone() {
  const { stdout } = await $`timedatectl show --property=Timezone --value`

  return stdout?.trim() || null
}
