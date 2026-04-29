import Stream from "./Stream.jsx"

import styles from "./styles.module.css"
import "./reader.js"
import { startLight, startBubbler, watch } from "../../../../lib/scope.js"
import { triggerDownload } from "../../helpers.js"

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
          />
        </div>
        <div>
          <h2>Bubbler</h2>
          <NumberInput
            name="bubler"
            value={bubbler_dac}
            onChange={onBubblerChange}
          />
        </div>
      </div>
      <div class={styles.preview}>
        <Stream
          controls={
            <button
              tooltip="Take capture"
              class={styles.button_capture}
              onClick={takeImage}
            >
              {cameraIcon}
            </button>
          }
        />
      </div>
    </>
  )
}

async function takeImage() {
  const url = new URL("/api/capture", document.URL)
  url.port = 80
  try {
    const res = await fetch(url, {
      method: "POST",
    })
    const body = await res.json()
    triggerDownload(body.url_jpeg)
  } catch (err) {
    console.error(err)
  }
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
