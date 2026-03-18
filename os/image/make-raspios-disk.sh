#!/bin/bash -eux

date=2025-12-04 # sync with setup.sh date
file=${date}-raspios-trixie-arm64-lite.img.xz
url=https://downloads.raspberrypi.com/raspios_lite_arm64/images/raspios_lite_arm64-${date}/${file}
device=$1
sha256="681a775e20b53a9e4c7341d748a5a8cdc822039d8c67c1fd6ca35927abbe6290"

# download raspios
wget -c -nc "${url}"

# download signature
wget -c -nc "${url}.sha256"

# make sure signature hasn't changed
head -c 64 "${file}.sha256"| grep -qx "${sha256}"

# verify signature
sha256sum --check "${file}.sha256"

# unmount
umount -q "${device}"? || true
umount -q "${device}" || true

# new empty dos partition table
echo 'label: dos' | sfdisk "$device"

# write raspios
# rpi-imager is also a thing worth considering; rpi-imager --cli
xzcat "$file" | dd bs=1M of="$device" status=progress conv=fdatasync

sudo partprobe "$device"

# find first partition
boot_partition=$(lsblk -ln -o NAME "$device" | sed -n '2p')

# mount boot partition
mount /dev/"${boot_partition}" /mnt

# configure
cp user-data.yaml /mnt/user-data

# unmount boot partition
umount /dev/"${boot_partition}"

echo "✅ Disk is ready."
