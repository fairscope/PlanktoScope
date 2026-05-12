#!/bin/bash -eux

sudo apt remove -y gcc g++ gcc-12 gcc-14 triggerhappy modemmanager mkvtoolnix libcap-dev libpython3-dev imgp gettext cloud-init bluez rpi-swap systemd-zram-generator rpi-usb-gadget
sudo apt autoremove -y
sudo apt clean -y

# FIXME: wrong method

# Clear machine-id so that it will be regenerated on the next boot
# This is also the condition for ConditionFirstBoot=yes
# (refer to https://www.freedesktop.org/software/systemd/man/latest/machine-id.html):
sudo bash -c 'printf "" > /var/lib/dbus/machine-id'
sudo bash -c 'printf "uninitialized\n" > /etc/machine-id'
