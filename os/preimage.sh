#!/bin/bash -eux

# https://systemd.io/BUILDING_IMAGES/
sudo rm -f /var/lib/systemd/random-seed
sudo rm -f /var/lib/systemd/credential.secret

sudo rm -f /etc/ssh/ssh_host_*_key*

uv clean --force
npm cache clean --force
rm -rf "$HOME"/.cache
mkdir "$HOME"/.cache

rm -f "$HOME"/.python_history
rm -f "$HOME"/.bash_history
rm -f "$HOME"/.gitconfig

rm -rf "$HOME"/.ssh
rm -rf "$HOME"/data
rm -f "$HOME"/filebrowser.db
rm -f "$HOME"/PlanktoScope/hardware.json
rm -f "$HOME"/PlanktoScope/config.json
rm -f "$HOME"/PlanktoScope/calibration.json

rm -rf /opt/PlanktoScope/documentation
sudo rm -rf /srv/docs


# FIXME: wrong method

# Clear machine-id so that it will be regenerated on the next boot
# This is also the condition for ConditionFirstBoot=yes
# (refer to https://www.freedesktop.org/software/systemd/man/latest/machine-id.html):
sudo bash -c 'printf "" > /var/lib/dbus/machine-id'
sudo bash -c 'printf "uninitialized\n" > /etc/machine-id'
