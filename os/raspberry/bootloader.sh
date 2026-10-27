#!/bin/bash -eux

# Disable automatic updates
# https://www.raspberrypi.com/documentation/computers/raspberry-pi.html#automaticupdates
sudo systemctl mask rpi-eeprom-update


# Update and configure the bootloader
# https://www.raspberrypi.com/documentation/computers/raspberry-pi.html#update-the-bootloader-configuration
# Please note that we disable self update on anything but Raspberry Pi 5; see config.ini

wget -P /tmp -c https://github.com/raspberrypi/rpi-eeprom/raw/f54693eca0a170bca62313cd781976e47bacdeb1/firmware-2712/default/pieeprom-2026-09-25.bin
wget -P /tmp -c https://github.com/raspberrypi/rpi-eeprom/raw/f54693eca0a170bca62313cd781976e47bacdeb1/firmware-2712/default/recovery.bin

rpi-eeprom-config /tmp/pieeprom-2026-09-25.bin --config boot.ini --out /tmp/pieeprom.upd
rpi-eeprom-digest -i /tmp/pieeprom.upd -o /tmp/pieeprom.sig

sudo mount -o remount,rw /boot/firmware
sudo cp /tmp/pieeprom.upd /tmp/pieeprom.sig /tmp/recovery.bin /boot/firmware/
sudo mount -o remount,ro /boot/firmware
