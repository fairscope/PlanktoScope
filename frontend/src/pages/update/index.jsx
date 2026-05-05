import "../../index.css"

// import styles from "./styles.module.css"
//
import { makeUrl } from "../../helpers.js"

// import "observable-polyfill"
import { createEventSource } from "eventsource-client"

import { createSignal, Show, Match, Switch } from "solid-js"

export default function Update() {
  const [upload_progress, set_upload_progress] = createSignal(0)
  const [bundle_info, set_bundle_info] = createSignal(null)
  const [status, set_status] = createSignal(null)

  async function handleSubmit(e) {
    e.preventDefault()
    console.time("install")
    install(bundle_info().path, ({ percentage, message, nesting_depth }) => {
      set_install_progress(percentage)
      set_install_message(message)
    })
      .catch((err) => {
        console.error(err)
      })
      .finally(() => {
        console.timeEnd("install")
      })
  }

  function handleFileChange(e) {
    e.preventDefault()
    const file = e.currentTarget.files[0]
    console.time("upload")
    upload(file, (p) => set_upload_progress(p))
      .then((bundle_info) => {
        console.log(bundle_info)
        set_bundle_info(bundle_info)
      })
      .catch((err) => {
        console.error(err)
      })
      .finally(() => {
        console.timeEnd("upload")
      })
  }

  createEventSource({
    url: makeUrl("/api/update/events"),
    onMessage: ({ data, event, id }) => {
      // console.log({ data, event, id })
      set_status(JSON.parse(data))
    },
  })

  return (
    <div>
      <h1>Software update</h1>
      <Show when={status() !== null}>
        <ul>
          <li>{`Operation: ${status().Operation}`}</li>
          <li>{`Last Error: ${status().LastError || "none"}`}</li>
        </ul>
      </Show>

      <form onSubmit={handleSubmit}>
        <input
          type="file"
          name="bundle"
          disabled={status()?.Operation !== "idle"}
          onChange={handleFileChange}
          required
          accept=".raucb"
        />
        <div>
          <p>{`Upload: ${upload_progress()}%`}</p>
          <progress max="100" value={upload_progress()} />
        </div>
        <Show when={bundle_info()}>
          <div>
            <p>{`version: ${bundle_info().version}`}</p>
            <p>{`build id: ${bundle_info().build}`}</p>
            <p>{`compatible: ${bundle_info().compatible}`}</p>
          </div>
        </Show>
        <Show when={status()?.Progress[1] !== "Checking bundle done."}>
          <div>
            <p>
              {`Status: ${status()?.Progress[0]}%`}{" "}
              <small>{status()?.Progress[1]}</small>
            </p>
            <progress max="100" value={status()?.Progress[0] || 0} />
          </div>
        </Show>
        <input
          type="submit"
          disabled={!bundle_info() || status()?.Operation !== "idle"}
          value="Install"
        />
        <input
          type="button"
          onClick={handleReboot}
          disabled={status()?.Progress[1] !== "Installing done."}
          value="Reboot"
        />
      </form>
    </div>
  )
}

// We use XMLHttpRequest because upload progress isn't supported outside of Chrome
// at the time of writing this
async function upload(blob, progress) {
  const xhr = new XMLHttpRequest()
  xhr.responseType = "json"
  return await new Promise((resolve, reject) => {
    xhr.upload.addEventListener("progress", (event) => {
      if (event.lengthComputable) {
        progress(Math.round((event.loaded / event.total) * 100))
      }
    })

    xhr.addEventListener("load", () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(xhr.response)
      } else {
        reject(new Error(`Upload failed with status "${xhr.status}".`))
      }
    })

    xhr.addEventListener("error", () => {
      reject(new Error("Network error"))
    })

    xhr.addEventListener("abort", () => {
      reject(new Error("Upload aborted"))
    })

    xhr.open("POST", makeUrl("/api/update/upload"), true)
    const form = new FormData()
    form.append("bundle", blob)
    xhr.send(form)
  })
}

async function install(path, progress) {
  await fetch(makeUrl("/api/update/install"), {
    method: "POST",
    body: JSON.stringify({ path }),
    headers: { "Content-Type": "application/json" },
  })
}

async function handleReboot() {
  await fetch(makeUrl("/api/update/reboot"), {
    method: "POST",
  })
  window.location = makeUrl("/")
}
