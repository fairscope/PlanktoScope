#!/bin/bash -eu

# This is an installation script to bootstrap installation of PlanktoScope OS.
# It is meant to be run on a specific Raspberry OS Pi OS standard installation.

line=$(head -n 1 /etc/rpi-issue)
reference="2025-12-04"
expected="Raspberry Pi reference $reference"

if [ "$line" != "$expected" ]; then
  echo "ERROR: Only Raspberry Pi OS $reference is supported."
  exit 1
fi

cd /home/pi
sudo apt install -y git just
if cd PlanktoScope; then
    git pull
else
    git clone https://github.com/fairscope/PlanktoScope.git
    cd PlanktoScope
fi
git submodule update --init
just
./os/postinstall.sh

echo "✅ Setup complete. Please reboot."
