# segmenter

The PlanktoScope's segmenter.

## Introduction

This repository contains the PlanktoScope's segmenter, which detects objects from camera frames and creates an image for each isolated object, with the background removed.

## Usage

### Deployment

The segmenter is published for deployment as a Docker container image at [https://ghcr.io/PlanktoScope/segmenter](https://github.com/fairscope/PlanktoScope/pkgs/container/segmenter). Note that the segmenter requires an MQTT broker accessible on the port 1883 of the host, as well as something to send MQTT commands to the segmenter.

### Development

Install all dependencies including development tooling:

```sh
cd controller
just
```

Start segmenter for development:

```sh
PLANKTOSCOPE_DATA_PATH=/home/pi/data just dev
# make changes and restart
```

Run the code auto-formatter on the project:

```sh
just format
```

Run all checks (including code formatting and linting):

```sh
just test
```

We have an [example dataset](https://drive.google.com/drive/folders/1g6OPaUIhYkU2FPqtIK4AW6U4FYmhFxuw) which you can use for testing the segmenter.

### Running on your computer

You will need a running MQTT broker. We recommend [Mosquitto](https://mosquitto.org/) with the following configuration

```
listener 1883
protocol mqtt

listener 9001
protocol websockets

allow_anonymous true
```

Then you can install and start the segmenter with

```sh
cd segmenter
uv sync
uv run main.py
```

### Prerequisites

To use this project, you'll need:

- Python >= 3.13.5
- uv

### API

### Start segmentation

**topic** `segmenter/segment`

**payload:**
```json
{
  "action": "segment",
  "path": "/home/pi/data/img/", // the acquisition path to segment
  "settings": {
    "force": false, // force re-segmentation of a segmented path
    "recursive": true, // traverse folders recursively
    "ecotaxa_export": true, // generate an ecotaxa export archive
    "keep": true, // save debug images - aka "/home/pi/data/clean"
    "process_id": "random-id" // the process id
    "process_min_ESD": 20, // the minimum object size (we use area-equivalent diameter)
    "remove_previous_mask": false, // see https://planktoscope.slack.com/archives/C01V5ENKG0M/p1714146253356569
  },
}
```

### Stop segmentation

**topic** `segmenter/segment`

**payload:**
```json
{
  "action": "stop",
}
```
