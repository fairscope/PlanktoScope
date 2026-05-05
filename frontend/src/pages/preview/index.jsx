import Stream from "./Stream.jsx"

import styles from "./styles.module.css"
import "./reader.js"
import {
  startLight,
  startBubbler,
  watch,
  stopBubbler,
} from "../../../../lib/scope.js"
import { triggerDownload, makeUrl } from "../../helpers.js"

import NumberInput from "./NumberInput.jsx"
import { createSignal } from "solid-js"

export default function Preview() {
  const [bubbler, setBubbler] = createSignal(false)
  const [light_dac, setLightDac] = createSignal(0)

  watch("status/bubbler").then(async (messages) => {
    for await (const message of messages) {
      setBubbler(message.status === "On")
    }
  })

  watch("status/light").then(async (messages) => {
    for await (const message of messages) {
      if (message.dac) {
        setLightDac(message.dac)
      }
    }
  })

  return (
    <>
      <div class={styles.controls}>
        <div>
          <h2>Light</h2>
          <NumberInput
            name="light"
            value={light_dac}
            onChange={onLightChange}
          />
        </div>
        <div>
          <h2>Bubbler</h2>
          <label for="bubbler">On/Off</label>
          <input
            type="checkbox"
            name="bubbler"
            checked={bubbler()}
            onChange={onBubblerChange}
          />
        </div>
      </div>
      <div class={styles.preview}>
        <Stream />
      </div>
    </>
  )
}

function onLightChange(value) {
  startLight({
    value,
  })
}

function onBubblerChange(event) {
  if (event.target.checked === true) {
    startBubbler()
  } else {
    stopBubbler()
  }
}
