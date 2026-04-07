import "../../index.css"
import styles from "./styles.module.css"

import { createSignal, onMount, onCleanup, Show } from "solid-js"
import { request, watch } from "../../../../lib/mqtt.js"

// Color-by options — keys that exist in each object of umap_projection.json
const COLOR_OPTIONS = [
  { key: "MeanHue", label: "Mean Hue" },
  { key: "MeanSaturation", label: "Mean Saturation" },
  { key: "MeanValue", label: "Mean Value (Brightness)" },
  { key: "equivalent_diameter", label: "Equivalent Diameter" },
  { key: "area", label: "Area" },
  { key: "eccentricity", label: "Eccentricity" },
  { key: "solidity", label: "Solidity" },
]

function loadPlotly() {
  return new Promise((resolve, reject) => {
    if (window.Plotly) return resolve(window.Plotly)
    const script = document.createElement("script")
    script.src = "/plotly-2.27.0.min.js"
    script.onload = () => resolve(window.Plotly)
    script.onerror = reject
    document.head.appendChild(script)
  })
}

export default function Similarity() {
  const [samples, setSamples] = createSignal([])
  const [selected, setSelected] = createSignal(null)
  const [colorBy, setColorBy] = createSignal("MeanHue")
  const [data, setData] = createSignal(null)
  const [status, setStatus] = createSignal("loading")
  const [hoverImg, setHoverImg] = createSignal(null)
  const [hoverPos, setHoverPos] = createSignal({ x: 0, y: 0 })

  let plotDiv
  let Plotly

  onMount(async () => {
    Plotly = await loadPlotly()

    // Fetch available UMAP projections
    try {
      const list = await request("similarity/list")
      setSamples(Array.isArray(list) ? list : [])
      if (list.length > 0) {
        setSelected(list[0])
        await loadProjection(list[0])
      } else {
        setStatus("empty")
      }
    } catch (err) {
      console.error("Failed to list projections:", err)
      setStatus("empty")
    }

    // Watch for live UMAP completion
    watch("status/segmenter/umap").then(async (messages) => {
      for await (const msg of messages) {
        if (msg.status === "ready" && msg.path) {
          // Refresh the sample list
          try {
            const list = await request("similarity/list")
            setSamples(Array.isArray(list) ? list : [])
            // Auto-select the new projection
            const newSample = list.find((s) => s.path.includes(msg.path))
            if (newSample) {
              setSelected(newSample)
              await loadProjection(newSample)
            }
          } catch (err) {
            console.error("Failed to refresh after UMAP:", err)
          }
        }
      }
    })
  })

  async function loadProjection(sample) {
    if (!sample) return
    setStatus("loading")
    try {
      const res = await fetch(sample.path)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const json = await res.json()
      setData(json)
      setStatus("ready")
      renderPlot(json, colorBy())
    } catch (err) {
      console.error("Failed to load projection:", err)
      setStatus("empty")
    }
  }

  function renderPlot(json, colorKey) {
    if (!Plotly || !plotDiv || !json?.objects?.length) return

    const objects = json.objects
    const x = objects.map((o) => o.umap_x)
    const y = objects.map((o) => o.umap_y)
    const colorValues = objects.map((o) => o[colorKey] ?? 0)
    const names = objects.map((o) => o.name)
    const hoverText = objects.map((o) => {
      const esd = o.equivalent_diameter?.toFixed(1) ?? "?"
      const area = o.area?.toFixed(0) ?? "?"
      return `${o.name}<br>ESD: ${esd} µm<br>Area: ${area} µm²`
    })

    const colorLabel =
      COLOR_OPTIONS.find((c) => c.key === colorKey)?.label || colorKey

    // Choose colorscale based on feature
    let colorscale = "Viridis"
    if (colorKey === "MeanHue") colorscale = "HSV"

    const trace = {
      x,
      y,
      mode: "markers",
      type: "scattergl",
      marker: {
        size: 5,
        color: colorValues,
        colorscale,
        colorbar: { title: colorLabel, thickness: 15 },
        opacity: 0.7,
      },
      text: hoverText,
      hoverinfo: "text",
      customdata: names,
    }

    const layout = {
      xaxis: { title: "UMAP 1", zeroline: false },
      yaxis: { title: "UMAP 2", zeroline: false },
      margin: { l: 50, r: 30, t: 30, b: 50 },
      hovermode: "closest",
      dragmode: "lasso",
      paper_bgcolor: "white",
      plot_bgcolor: "#fafafa",
    }

    const config = {
      responsive: true,
      displayModeBar: true,
      modeBarButtonsToAdd: ["lasso2d", "select2d"],
      scrollZoom: true,
    }

    Plotly.newPlot(plotDiv, [trace], layout, config)

    // Show thumbnail on hover
    plotDiv.on("plotly_hover", (eventData) => {
      const point = eventData.points[0]
      if (!point) return
      const name = point.customdata
      const sample = selected()
      if (sample) {
        setHoverImg(`${sample.images_path}/${name}.jpg`)
        setHoverPos({
          x: eventData.event.clientX + 15,
          y: eventData.event.clientY + 15,
        })
      }
    })

    plotDiv.on("plotly_unhover", () => {
      setHoverImg(null)
    })
  }

  function onSampleChange(e) {
    const idx = parseInt(e.target.value)
    const sample = samples()[idx]
    setSelected(sample)
    loadProjection(sample)
  }

  function onColorChange(e) {
    const key = e.target.value
    setColorBy(key)
    const d = data()
    if (d) renderPlot(d, key)
  }

  return (
    <>
      <header data-theme="light">
        <h1>Similarity</h1>
      </header>

      <main data-theme="light">
        <div class={styles.container}>
          <div class={styles.controls}>
            <div>
              <label for="sample-select">Sample</label>
              <select id="sample-select" onChange={onSampleChange}>
                {samples().map((s, i) => (
                  <option value={i}>{s.label || s.path}</option>
                ))}
              </select>
            </div>

            <div>
              <label for="color-select">Color by</label>
              <select id="color-select" onChange={onColorChange}>
                {COLOR_OPTIONS.map((opt) => (
                  <option value={opt.key} selected={opt.key === colorBy()}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>

            <Show when={data()}>
              <span class={`${styles.status} ${styles.status_ready}`}>
                {data().n_objects} objects, {data().n_features} features
              </span>
            </Show>

            <Show when={status() === "loading"}>
              <span
                class={`${styles.status} ${styles.status_loading}`}
                aria-busy="true"
              >
                Loading...
              </span>
            </Show>

            <Show when={status() === "empty" && samples().length === 0}>
              <span class={`${styles.status} ${styles.status_empty}`}>
                No UMAP projections available. Run a segmentation first.
              </span>
            </Show>
          </div>

          <div ref={plotDiv} class={styles.plot} />

          <Show when={hoverImg()}>
            <div
              class={styles.thumbnail_popup}
              style={{
                left: `${hoverPos().x}px`,
                top: `${hoverPos().y}px`,
              }}
            >
              <img src={hoverImg()} alt="Object thumbnail" loading="lazy" />
            </div>
          </Show>
        </div>
      </main>
    </>
  )
}
