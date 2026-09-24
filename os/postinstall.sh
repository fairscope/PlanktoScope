#!/bin/bash -eux

sudo apt remove --yes gcc g++ gcc-12 gcc-14 triggerhappy modemmanager mkvtoolnix libcap-dev libpython3-dev imgp gettext cloud-init bluez rpi-swap systemd-zram-generator rpi-usb-gadget tmux just gdisk bmaptool libguestfs-tools
sudo apt autoremove --purge --yes
sudo apt clean --yes
