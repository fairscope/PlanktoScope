import "../../index.css"

// import styles from "./styles.module.css"

import { createSignal, Show, Match, Switch } from "solid-js"

export default function Update() {
  const [upload_progress, set_upload_progress] = createSignal(0)
  const [install_progress, set_install_progress] = createSignal(0)
  const [bundle_info, set_bundle_info] = createSignal(null)

  async function handleSubmit(e) {
    e.preventDefault()
    console.time("install")
    install(bundle_info().path, (p) => set_install_progress(p))
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

  return (
    <div>
      <h1>Software update</h1>
      <form onSubmit={handleSubmit}>
        <input
          type="file"
          name="bundle"
          onChange={handleFileChange}
          required
          accept=".raucb"
        />
        <div>
          <label for="progress-upload">{`Upload: ${upload_progress()}%`}</label>
          <input
            type="range"
            readonly
            disabled
            name="progress-upload"
            step="1"
            min="0"
            max="100"
            value={upload_progress()}
          />
        </div>
        <Show when={bundle_info()}>
          <div>
            <p>{`version: ${bundle_info().version}`}</p>
            <p>{`build id: ${bundle_info().build}`}</p>
            <p>{`compatible: ${bundle_info().compatible}`}</p>
          </div>
        </Show>
        <div>
          <label for="progress-install">{`Install: ${install_progress()}%`}</label>
          <input
            type="range"
            readonly
            disabled
            name="progress-install"
            step="1"
            min="0"
            max="100"
            value={install_progress()}
          />
        </div>
        <input type="submit" disabled={!bundle_info()} value="Install" />
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

    const url = new URL("/api/update/upload", document.URL)
    url.port = 80
    xhr.open("POST", url, true)
    const form = new FormData()
    form.append("bundle", blob)
    xhr.send(form)
  })
}

async function install(path, progress) {
  const url = new URL("/api/update/install", document.URL)
  url.port = 80
  await fetch(url, {
    method: "POST",
    body: JSON.stringify({ path }),
    headers: { "Content-Type": "application/json" },
  })
  watchProgress(progress)

  const deferred = Promise.withResolvers()
  ;(() => {
    const url = new URL("/api/update/events", document.URL)
    url.port = 80
    const es = new EventSource(url)
    es.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        progress(data[0])
        if (data[0] === 100) {
          deferred.resolve()
          es.close()
        }
      } catch (err) {
        deferred.reject(err)
      }
    }

    es.onerror = (err) => {
      deferred.reject(err)
    }
  })()

  return deferred.promise
}

async function watchProgress(progress) {}
