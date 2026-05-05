import { createAsync, query } from "@solidjs/router"
import { getMachineName } from "../../../lib/identity"

function wait(ms, data) {
  return new Promise((resolve) => setTimeout(resolve, ms, data))
}

function random(min, max) {
  return Math.floor(Math.random() * (max - min + 1)) + min
}

const getName = query(() => wait(random(500, 1000), "Solid"), "aboutName")

const AboutData = () => {
  return createAsync(() => getMachineName())
}

export default AboutData
