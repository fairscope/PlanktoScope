/* globals MediaMTXWebRTCReader */

import Zoomist from "zoomist"
import "zoomist/css"

import styles from "./Stream.module.css"
import "./reader.js"

import fullscreenIcon from "./fullscreen.svg"

export default function Stream(props) {
  let zoomist_container
  let loader_container
  let stream_container

  const video = (
    <video
      on:loadedmetadata={onVideoLoad}
      class={styles.video}
      muted
      autoplay
      disablepictureinpicture
      preload="auto"
    />
  )

  function onVideoLoad() {
    stream_container.style.display = "flex"
    loader_container.style.display = "none"
    new Zoomist(zoomist_container, {
      slider: true,
      zoomer: true,
      maxScale: 4,
      zoomRatio: 0.1,
    })
  }

  const url = new URL(document.location)
  url.port = 8889
  url.pathname = "/cam/whep"
  const reader = new MediaMTXWebRTCReader({
    url,
    onError: (err) => {
      console.error("mediamtx error", err)
    },
    onTrack: (evt) => {
      console.debug("mediamtx track", evt)
      video.srcObject = evt.streams[0]
    },
    onDataChannel: (evt) => {
      evt.channel.binaryType = "arraybuffer"
      evt.channel.onmessage = (evt) => {
        console.log("data channel message", evt.data)
      }
    },
  })

  window.addEventListener("beforeunload", () => {
    reader?.close()
  })

  function fullscreen() {
    if (document.fullscreenElement) {
      document.exitFullscreen().catch(console.error)
    } else {
      stream_container
        .requestFullscreen({ navigationUI: "hide" })
        .catch(console.error)
    }
  }

  return (
    <>
      <div ref={loader_container} class={styles.loader_container}>
        <span class={styles.loader} />
      </div>
      <div
        ref={stream_container}
        style={{ display: "none" }}
        class={styles.stream_container}
      >
        <div ref={zoomist_container} class="zoomist-container">
          <div class="zoomist-wrapper">
            <div class="zoomist-image">{video}</div>
          </div>
          <button
            tooltip="Take capture"
            class={styles.button_fullscreen}
            onClick={fullscreen}
          >
            {fullscreenIcon}
          </button>
          {props.controls}
        </div>
      </div>
    </>
  )
}
