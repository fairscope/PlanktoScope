import { hostname } from "os"

const prefix = "planktoscope-"
export function getMachineName() {
  const hostname = getHostname()
  return hostname.startsWith(prefix) ? hostname.slice(prefix.length) : hostname
}

export function getHostname() {
  return hostname()
}
