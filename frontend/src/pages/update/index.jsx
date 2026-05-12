import "../../index.css"

import { makeUrl } from "../../helpers.js"
import { request, observe } from "../../../../lib/mqtt.js"

import { createSignal, Show } from "solid-js"

export default function Update() {
  const [upload_progress, set_upload_progress] = createSignal(0)
  const [bundle_info, set_bundle_info] = createSignal(null)
  const [status, set_status] = createSignal(null)
  const [update_available, set_update_available] = createSignal(null)
  const [checking_for_update, set_checking_for_update] = createSignal(false)

  function handleInstall() {
    console.time("install")
    request("software-updater", { action: "install", uri: bundle_info().uri })
      .catch((err) => {
        console.error(err)
      })
      .finally(() => {
        console.timeEnd("install")
      })
  }

  function handleFileChange(evt) {
    const file = evt.currentTarget.files[0]
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

  function handlePoll() {
    set_checking_for_update(true)
    request("software-updater", { action: "poll" })
      .catch(console.error)
      .finally(() => {
        set_checking_for_update(false)
      })
  }

  observe("software-updater/status").forEach(set_status)
  observe("software-updater/update-available").forEach(([bool, bundle]) => {
    set_update_available(bool)
    set_bundle_info(bundle)
  })

  return (
    <div>
      <h1>Software update</h1>
      <div>
        <h2>Status</h2>
        <Show when={status() !== null}>
          <ul>
            <li>{`Operation: ${status().Operation}`}</li>
            <li>{`Last Error: ${status().LastError || "none"}`}</li>
          </ul>
          <p>
            {`Progress: ${status()?.Progress[0] ?? 0}%`}{" "}
            <small>{status()?.Progress[1]}</small>
          </p>
          <progress max="100" value={status()?.Progress[0] || 0} />
        </Show>

        <Show when={bundle_info()}>
          <ul>
            <li>
              {`version: `}
              <code>{bundle_info().version}</code>
            </li>{" "}
            <li>
              {`build id: `}
              <code>{bundle_info().build}</code>
            </li>
            <li>
              {`compatible: `}
              <code>{bundle_info().compatible}</code>
            </li>
            <li>
              {`uri: `}
              <code>{bundle_info().uri}</code>
            </li>
          </ul>
        </Show>
      </div>

      <hr />

      <div>
        <h2>Actions</h2>
        <p>
          <button
            onClick={handleInstall}
            disabled={!bundle_info() || status()?.Operation !== "idle"}
          >
            Install
          </button>
        </p>
        <p>
          <button
            onClick={handleReboot}
            disabled={status()?.Progress[1] !== "Installing done."}
          >
            Restart
          </button>
        </p>
      </div>

      <hr />

      <div>
        <h2>Online update</h2>
        <p>
          Update available:{" "}
          {update_available() === null
            ? "unknown"
            : update_available()
              ? "yes"
              : "no"}
        </p>
        <button onClick={handlePoll} aria-busy={checking_for_update()}>
          Check for update
        </button>
      </div>

      <hr />

      <div>
        <h2>Offline update</h2>
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
      </div>
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

async function handleReboot() {
  await request("software-updater", { action: "reboot" })
  window.location = makeUrl("/")
}
