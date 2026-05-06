import Stream from "./Stream.jsx"

import styles from "./styles.module.css"
import "./reader.js"
import { startLight, startBubbler, watch } from "../../../../lib/scope.js"
import { triggerDownload, makeUrl } from "../../helpers.js"

import cameraIcon from "./camera.svg"

import NumberInput from "./NumberInput.jsx"
import { createSignal } from "solid-js"

export default function Preview() {
  const [bubbler_dac, setBubblerDac] = createSignal(0)
  const [light_dac, setLightDac] = createSignal(0)

  watch("status/bubbler").then(async (messages) => {
    for await (const message of messages) {
      if (message.dac) {
        setBubblerDac(message.dac)
      }
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
            min="0"
            max="1"
            step="0.1"
          />
        </div>
        <div>
          <h2>Bubbler</h2>
          <NumberInput
            name="bubler"
            value={bubbler_dac}
            onChange={onBubblerChange}
            min="0"
            max="100"
            step="25"
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
