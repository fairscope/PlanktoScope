#!/bin/bash -eux

sudo mount -o remount,rw /boot/firmware

# Configure firmware
# https://www.raspberrypi.com/documentation/computers/config_txt.html
sudo bash -c "cat \"config.ini\" >> \"/boot/firmware/config.txt\""

# Disable the 4 Raspberry logo in the top left corner
# more space for kernel and system logs
[ ! -f /boot/firmware/cmdline-A.txt ] || \
  grep -qw logo.nologo /boot/firmware/cmdline-A.txt || \
  sudo sed -i 's/$/ logo.nologo/' /boot/firmware/cmdline-A.txt

[ ! -f /boot/firmware/cmdline-B.txt ] || \
  grep -qw logo.nologo /boot/firmware/cmdline-B.txt || \
  sudo sed -i 's/$/ logo.nologo/' /boot/firmware/cmdline-B.txt

[ ! -f /boot/firmware/cmdline.txt ] || \
  grep -qw logo.nologo /boot/firmware/cmdline.txt || \
  sudo sed -i 's/$/ logo.nologo/' /boot/firmware/cmdline.txt

sudo mount -o remount,ro /boot/firmware
