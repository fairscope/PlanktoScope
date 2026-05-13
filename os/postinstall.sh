#!/bin/bash -eux

sudo apt remove -y gcc g++ gcc-12 gcc-14 triggerhappy modemmanager mkvtoolnix libcap-dev libpython3-dev imgp gettext cloud-init bluez rpi-swap systemd-zram-generator rpi-usb-gadget git tmux just
sudo apt autoremove -y
sudo apt clean -y
