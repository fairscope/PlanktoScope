import { $ as execa } from "execa"

export async function $(...args) {
  return execa(...args)
}
