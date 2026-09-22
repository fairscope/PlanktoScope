# reporter

The PlanktoScope's PDF report generator.

## Introduction

This service renders a self-contained PDF acquisition report for one or more
segmented acquisitions. It reads each acquisition's `metadata.json`, its EcoTaxa
TSV, the flat-field image and a selection of ROI thumbnails, recomputes the same
quality-control statistics the Validation dashboard shows, draws the charts with
matplotlib, and converts an HTML template to PDF with WeasyPrint. Everything —
fonts, images and charts — is embedded, so the report renders offline in the
field and needs no external assets.

The report is triggered from the dashboard's "Report export" dialog over MQTT and
written to `/home/pi/data/reports/`, where the dashboard serves it for download.

## Usage

### Development

Install runtime dependencies and (re)install the systemd service:

```sh
cd reporter
just setup
```

Install all dependencies including development tooling:

```sh
just setup-dev
```

Start the reporter for development (stops the service first):

```sh
just dev
# make changes and restart
```

Run the code auto-formatter on the project:

```sh
just format
```

Run all checks (formatting and linting):

```sh
just test
```

### Prerequisites

To use this project, you'll need:

- Python >= 3.13.5
- uv
- Pango and harfbuzz-subset (WeasyPrint's native dependencies — `just setup`
  installs them)

An MQTT broker must be reachable on port 1883 of the host. We recommend
[Mosquitto](https://mosquitto.org/).

### Rendering without MQTT

For local iteration you can render straight from a dialog payload, bypassing the
broker:

```sh
uv run main.py --payload '{"acquisition_paths":["/home/pi/data/img/<date>/<sample>/<acq>"]}'
```

The output directory defaults to `/home/pi/data/reports` and can be overridden
with the `REPORTER_OUTPUT` environment variable.

## API

The reporter subscribes to `actuator/reporter/generate` and publishes progress to
`status/reporter`.

### Generate a report

**topic** `actuator/reporter/generate`

**payload** (combined report — one PDF covering a selection of acquisitions, as
sent by the "Report export" dialog):

```json
{
  "action": "generate",
  "acquisition_paths": [
    "/home/pi/data/img/<date>/<sample>/<acq>"
  ],
  "sections": { "...": "which report sections to include (optional)" },
  "gallery": { "...": "object-gallery options (optional)" }
}
```

A legacy single-acquisition payload is also accepted; it produces the full report
plus a one-page summary:

```json
{
  "action": "generate",
  "acquisition_path": "/home/pi/data/img/<date>/<sample>/<acq>"
}
```

### Status

**topic** `status/reporter`

While working the reporter publishes `{"status": "generating", ...}`. On success
it publishes the download location:

```json
{
  "status": "done",
  "filename": "<project>_<sample>_<acq>_report.pdf",
  "url": "/api/files/reports/<project>_<sample>_<acq>_report.pdf"
}
```

On failure it publishes `{"status": "error", "error": "<message>"}`.

## Licensing

Except where otherwise indicated, source code provided here is covered by the
following information:

Copyright PlanktoScope project contributors

SPDX-License-Identifier: GPL-3.0-or-later

You can use the source code provided here under the [GPL 3.0 License](https://www.gnu.org/licenses/gpl-3.0.en.html).

Bundled IBM Plex fonts in `fonts/` are licensed under the SIL Open Font License;
see `fonts/LICENSE-IBMPlex.txt`.
