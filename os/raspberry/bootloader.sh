#!/bin/bash -eux

# Disable automatic updates
# https://www.raspberrypi.com/documentation/computers/raspberry-pi.html#automaticupdates
sudo systemctl mask rpi-eeprom-update


# Update and configure the bootloader
# https://www.raspberrypi.com/documentation/computers/raspberry-pi.html#update-the-bootloader-configuration
# Please note that we disable self update on anything but Raspberry Pi 5; see config.ini

wget -P /tmp -c https://github.com/raspberrypi/rpi-eeprom/raw/8fb9ea2fcb1735616a72fe6c5eb15b96595fc35d/firmware-2712/old/default/pieeprom-2025-12-08.bin
wget -P /tmp -c https://github.com/raspberrypi/rpi-eeprom/raw/8fb9ea2fcb1735616a72fe6c5eb15b96595fc35d/firmware-2712/latest/recovery.bin

rpi-eeprom-config /tmp/pieeprom-2025-12-08.bin --config boot.ini --out /tmp/pieeprom.upd
rpi-eeprom-digest -i /tmp/pieeprom.upd -o /tmp/pieeprom.sig

sudo mount -o remount,rw /boot/firmware
sudo cp /tmp/pieeprom.upd /tmp/pieeprom.sig /tmp/recovery.bin /boot/firmware/
sudo mount -o remount,ro /boot/firmware
