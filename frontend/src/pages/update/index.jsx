import "../../index.css"

// import styles from "./styles.module.css"

import { createSignal } from "solid-js"

export default function Update() {
  const [upload_progress, set_upload_progress] = createSignal(0)
  const [install_progress, set_install_progress] = createSignal(0)

  function handleUploadProgress(p) {
    set_upload_progress(p)
  }

  const url = new URL("/api/update/events", document.URL)
  url.port = 80
  const es = new EventSource(url)
  es.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data)
      console.log(data)
      set_install_progress(data[0])
    } catch (err) {
      console.error(err)
    }
  }

  es.onerror = (err) => {
    console.error(err)
  }

  function handleSubmit(e) {
    e.preventDefault()
    const file = e.currentTarget.elements.bundle.files[0]
    console.time("upload")
    upload(file, handleUploadProgress)
      .then((bundle_info) => {
        console.log("success", bundle_info)
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
        <input type="file" name="bundle" required accept=".raucb" />
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
        <input type="submit" value="Update" />
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

    const url = new URL("/api/update", document.URL)
    url.port = 80
    xhr.open("POST", url, true)
    const form = new FormData()
    form.append("bundle", blob)
    xhr.send(form)
  })
}
