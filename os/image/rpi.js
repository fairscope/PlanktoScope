import { $ } from "execa"

export async function setTryBootFlag(bool) {
  await $`vcmailbox 0x00038064 4 0 ${bool ? "1" : "0"}`
}

export async function getTryBootFlag() {
  const { stdout } = await $`vcmailbox 0x00038064 4 0`
  console.log(stdout)
  /*
   * Parse output.
   *
   * If the reboot flag is unset:
   *
   * 	$ vcmailbox 0x00030064 4 0 0
   * 	0x0000001c 0x80000000 0x00030064 0x00000004 0x80000004 0x00000000 0x00000000
   *
   * If the reboot flag is set:
   *
   * 	$ vcmailbox 0x00030064 4 0 0
   * 	0x0000001c 0x80000000 0x00030064 0x00000004 0x80000004 0x00000001 0x00000000
   */

  const [, , , , word] = stdout.split(" ")
  const value = parseInt(words, 0) >>> 0 // >>> 0 coerces to uint32
  return value !== 0
}

if (import.meta.main) {
  const a = await getTryBootFlag()
  console.log(a)
  await setTryBootFlag(!a)

  const b = await getTryBootFlag()
  console.lob(b)

  console.log(a === b)
}
