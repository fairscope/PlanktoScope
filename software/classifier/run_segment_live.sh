#!/bin/bash
# 1. Activate the environment
source /home/pi/hailo_env/bin/activate
# 2. Move to the classifier directory
cd /home/pi/PlanktoScope/segmenter/classifier
# 3. Debug: Log what we received
echo "DEBUG: arg1='$1' arg2='$2'" >> /tmp/segment_debug.log
# 4. Clean the image path (remove newlines/whitespace)
IMAGE_PATH=$(echo "$1" | tr -d '\n\r' | xargs)
echo "DEBUG: cleaned IMAGE_PATH='$IMAGE_PATH'" >> /tmp/segment_debug.log
# 5. Run the python script
python3 segment_live.py "$IMAGE_PATH" "$2"
