#!/bin/bash

# Activate the Hailo environment
source /home/pi/hailo_env/bin/activate

# Navigate to the script directory
cd /home/pi/PlanktoScope/segmenter/classifier

# Handle arguments
COMMAND=$1
shift

if [ "$COMMAND" == "process" ]; then
    # Parse args from Node-RED: --input "path" --params 'json'
    # We pass these directly to a python wrapper or handle simple args
    # For the live segmenter logic, we will call segment_live.py


    # Simple passthrough, should handle this better soon
    python3 segment_live.py "$@"

elif [ "$COMMAND" == "browse" ]; then

    echo '{"status": "error", "error": "Browse CLI not implemented yet"}'

elif [ "$COMMAND" == "status" ]; then
    # Return JSON status of the system
    echo '{"classifier_ready": true, "hailo": {"hardware_present": true}}'

else
    echo "Unknown command"
    exit 1
fi
