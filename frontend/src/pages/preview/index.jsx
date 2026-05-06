import Stream from "./Stream.jsx"

import styles from "./styles.module.css"
import "./reader.js"
import { startLight, startBubbler, watch } from "../../../../lib/scope.js"
import { triggerDownload, makeUrl } from "../../helpers.js"

import NumberInput from "./NumberInput.jsx"
import { createSignal } from "solid-js"

export default function Preview() {
  const [bubbler_value, setBubblerValue] = createSignal(0)
  const [light_value, setLightValue] = createSignal(0)

  watch("status/bubbler").then(async (messages) => {
    for await (const message of messages) {
      if (message.value) {
        setBubblerValue(message.value)
      }
    }
  })

  watch("status/light").then(async (messages) => {
    for await (const message of messages) {
      if (message.value) {
        setLightValue(message.value)
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
            value={light_value}
            onChange={onLightChange}
            step="0.01"
          />
        </div>
        <div>
          <h2>Bubbler</h2>
          <NumberInput
            name="bubler"
            value={bubbler_value}
            onChange={onBubblerChange}
            step="0.25"
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

function onBubblerChange(value) {
  startBubbler({
    value,
  })
}
