#!/bin/bash
# Script to create /etc/sysctl.d/99-h264-stream.conf for H.264 UDP streaming
# Automatically detects Raspberry Pi 4 or 5
# Run as root: sudo ./setup_h264_sysctl.sh
# Avoids packet loss between picamera2 and MediaMTX which cause corrupted frames
# https://mediamtx.org/docs/usage/decrease-packet-loss

CONF_FILE="/etc/sysctl.d/99-h264-stream.conf"

# Detect Pi model
PI_MODEL=$(awk -F': ' '/Model/ {print $2}' /proc/device-tree/model)
echo "Detected Pi model: $PI_MODEL"

if [[ "$PI_MODEL" == *"Raspberry Pi 5"* ]]; then
    RMEM_MAX=33554432       # 32 MB
    RMEM_DEFAULT=16777216   # 16 MB
    UDP_MEM="131072 262144 524288"
    NETDEV_MAX_BACKLOG=250000
else
    RMEM_MAX=16777216       # 16 MB
    RMEM_DEFAULT=8388608    # 8 MB
    UDP_MEM="65536 131072 262144"
    NETDEV_MAX_BACKLOG=100000
fi

# Write sysctl config file
echo "Writing $CONF_FILE..."
cat <<EOF > $CONF_FILE
# H.264 streaming tuning for Picamera2 -> MediaMTX
net.core.rmem_max=$RMEM_MAX
net.core.rmem_default=$RMEM_DEFAULT
net.ipv4.udp_mem=$UDP_MEM
net.core.netdev_max_backlog=$NETDEV_MAX_BACKLOG
EOF

# Apply settings immediately
echo "Applying sysctl settings..."
sysctl --system

echo "Done! Sysctl configuration written to $CONF_FILE and applied."
