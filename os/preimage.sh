#!/bin/bash -eux

# https://systemd.io/BUILDING_IMAGES/
sudo rm -f /var/lib/systemd/random-seed
sudo rm -f /var/lib/systemd/credential.secret

sudo rm -f /etc/ssh/ssh_host_*_key*

uv clean --force
npm cache clean --force

# Outdated and takes a lot of space
rm -rf /opt/PlanktoScope/documentation
rm -rf /opt/PlanktoScope/hardware
rm -rf /opt/PlanktoScope/.git
