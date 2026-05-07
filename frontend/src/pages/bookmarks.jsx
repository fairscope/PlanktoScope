import "../index.css"

import { makeUrl, makeLocalUrl } from "../helpers.js"

export default function Bookmarks() {
  return (
    <>
      <header>
        <h1>Bookmarks</h1>
      </header>

      <main>
        <h2>Users</h2>

        <ul>
          <li>
            <a href={makeLocalUrl("/")} target="_blank">
              Dashboard
            </a>
          </li>
          <li>
            <a href={makeUrl("/ps/data/browse/files/")} target="_blank">
              Gallery
            </a>
          </li>
          <li>
            <a href={makeLocalUrl("/update")} target="_blank">
              Update software
            </a>
          </li>
        </ul>

        <h2>Developers</h2>

        <ul>
          <li>
            <a
              href="https://www.figma.com/design/KXH3qkalr7eeFbyGsutZKt/PlanktoScope-Dashboard-v2"
              target="_blank"
            >
              Figma
            </a>
          </li>
          <li>
            <a href={makeUrl("/admin/cockpit/system/logs")} target="_blank">
              Logs
            </a>
          </li>
          <li>
            <a href={makeUrl("/admin/cockpit/system/terminal")} target="_blank">
              Terminal
            </a>
          </li>

          <li>
            <a href={makeUrl("/admin/cockpit/metrics")} target="_blank">
              Metrics
            </a>
          </li>

          <li>
            <a href={makeUrl("/admin/cockpit/")} target="_blank">
              Cockpit
            </a>
          </li>
          <li>
            <a href={makeUrl("/admin/cockpit/files/")} target="_blank">
              File Browser
            </a>
          </li>
          <li>
            <a href={makeUrl("/admin/ps/node-red-v2/")} target="_blank">
              Node-RED flow editor
            </a>
          </li>
          <li>
            <a href={makeLocalUrl("/factory")} target="_blank">
              Factory
            </a>
          </li>
          <li>
            <a href={makeLocalUrl("/setup")} target="_blank">
              Setup
            </a>
          </li>
          <li>
            <a href={makeUrl("/ps/node-red-v2/dashboard/")} target="_blank">
              Node-RED Dashboard
            </a>
          </li>
          <li>
            <a href={makeLocalUrl("/preview/node-red")} target="_blank">
              Node-RED preview
            </a>
          </li>
        </ul>

        <h2>Experiments</h2>

        <ul>
          <li>
            <a href={makeLocalUrl("/network")} target="_blank">
              Network
            </a>
          </li>
          <li>
            <a href={makeLocalUrl("/preview")} target="_blank">
              Preview
            </a>
          </li>
          <li>
            <a href={makeLocalUrl("/gallery")} target="_blank">
              Ecotaxa Project Gallery
            </a>
          </li>
          <li>
            <a href={makeLocalUrl("/developer-mode")} target="_blank">
              Developer Mode
            </a>
          </li>
        </ul>
      </main>
    </>
  )
}
