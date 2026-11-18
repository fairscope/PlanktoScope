#!/bin/bash -eux

sudo apt remove --yes mkvtoolnix cloud-init bluez rpi-swap systemd-zram-generator rpi-usb-gadget htop build-essential apparmor cpp cpp-14 gcc gcc-14 7zip
sudo apt autoremove --purge --yes
sudo apt clean --yes
