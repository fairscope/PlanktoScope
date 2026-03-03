#!/bin/bash -eu
# shellcheck disable=all

machine_name="$(cat /run/machine-name)"
hostname="planktoscope-${machine_name}"

mkdir -p /etc
echo "Hostname: $hostname"
printf "%s" "$hostname" > /etc/hostname

sed -i "s/raspberrypi/$hostname/g" /etc/hosts || true
sed -i "s/raspberrypi/PlanktoScope $machine_name/g" /etc/NetworkManager/system-connections/wlan0-hotspot.nmconnection || true
