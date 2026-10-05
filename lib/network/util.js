import { $ } from "../exec"

export async function pingWired(interf, host) {
  try {
    await $`ping -c 1 -I ${interf} ${host}`
    return true
  } catch {
    return false
  }
}
