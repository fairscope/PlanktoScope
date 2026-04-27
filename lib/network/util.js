import { execa } from "execa"

export async function pingWired(interf, host) {
  try {
    await execa("ping", ["-c", "1", "-I", interf, host])
    return true
  } catch {
    return false
  }
}
