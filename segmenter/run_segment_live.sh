#!/bin/bash
# Run live segmentation on a single image
# Called by the imager controller after each frame capture

IMAGE_PATH=$(echo "$1" | tr -d '\n\r' | xargs)

if [ -z "$IMAGE_PATH" ]; then
    echo '{"error": "No image path provided"}'
    exit 1
fi

cd /home/pi/PlanktoScope/segmenter
/usr/local/bin/uv run python segment_live.py "$IMAGE_PATH"
