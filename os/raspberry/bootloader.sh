#!/bin/bash -eux

# Disable automatic updates
# https://www.raspberrypi.com/documentation/computers/raspberry-pi.html#automaticupdates
sudo systemctl mask rpi-eeprom-update


# Update and configure the bootloader
# https://www.raspberrypi.com/documentation/computers/raspberry-pi.html#update-the-bootloader-configuration
# Please note that we disable self update on anything but Raspberry Pi 5; see config.ini

sudo apt install -y rpi-eeprom

cp /usr/lib/firmware/raspberrypi/bootloader-2712/default/pieeprom-2025-12-08.bin /tmp
cp /usr/lib/firmware/raspberrypi/bootloader-2712/default/recovery.bin /tmp

rpi-eeprom-config /tmp/pieeprom-2025-12-08.bin --config boot.ini --out /tmp/pieeprom.upd
rpi-eeprom-digest -i /tmp/pieeprom.upd -o /tmp/pieeprom.sig

sudo mount -o remount,rw /boot/firmware
sudo cp /tmp/pieeprom.upd /tmp/pieeprom.sig /tmp/recovery.bin /boot/firmware/
sudo mount -o remount,ro /boot/firmware
