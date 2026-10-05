#!/bin/bash -eu
# shellcheck disable=all

machine_name="$(cat /run/machine-name)"
hostname="planktoscope-${machine_name}"

mkdir -p /etc
echo "Hostname: $hostname"
printf "%s" "$hostname" > /etc/hostname
