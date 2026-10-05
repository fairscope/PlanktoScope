#!/bin/bash -eu

# This is an installation script to bootstrap installation of PlanktoScope OS.
# It is meant to be run on a specific Raspberry OS Pi OS standard installation.

line=$(head -n 1 /etc/rpi-issue)
reference="2026-06-18"
expected="Raspberry Pi reference $reference"

if [ "$line" != "$expected" ]; then
  echo "ERROR: Only Raspberry Pi OS $reference is supported."
  exit 1
fi

sudo mount -o remount,rw /boot/firmware
sudo apt update -y
sudo apt install -y git just
cd /opt
if cd PlanktoScope; then
    git pull
else
    sudo mkdir PlanktoScope
    sudo chown pi:pi PlanktoScope
    git clone https://github.com/fairscope/PlanktoScope.git
    cd PlanktoScope
fi
git submodule update --init
just
./os/postinstall.sh

echo "✅ Setup complete. Please reboot."
