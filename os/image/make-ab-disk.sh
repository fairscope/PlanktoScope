#!/bin/bash -eux

if [ "$EUID" -ne 0 ]; then
    echo "Please run as root"
    exit 1
fi

date=2025-12-04 # sync with setup.sh date
file=${date}-raspios-trixie-arm64-lite.img.xz
url=https://downloads.raspberrypi.com/raspios_lite_arm64/images/raspios_lite_arm64-${date}/${file}
device=$1
sha256="681a775e20b53a9e4c7341d748a5a8cdc822039d8c67c1fd6ca35927abbe6290"
img="${file%.xz}"

# download raspios
wget -c -nc "${url}"

# download signature
wget -c -nc "${url}.sha256"

# make sure signature hasn't changed
head -c 64 "${file}.sha256"| grep -qx "${sha256}"

# verify signature
sha256sum --check "${file}.sha256"

# unmount
./umount.js "${device}"

# Removes existing GPT/MBR data.
sgdisk --zap-all "${device}"

# Create a new partition table
sgdisk --new "${device}"

# 1:set:0 -A 1:set:1
# sets hidden and firmware GPT flags

# Partition 1: 8MB FAT12 "AUTOBOOT"
sgdisk --new=1:0:+8M --typecode=1:0700 -A 1:set:0 -A 1:set:1 --change-name=1:"AUTOBOOT" "${device}"

# Partition 2: 512MB FAT32 "BOOTFS A"
sgdisk --new=2:0:+512M --typecode=2:0700 -A 2:set:0 -A 2:set:1 --change-name=2:"BOOTFS A" "${device}"

# Partition 3: 512MB FAT32 "BOOTFS B"
sgdisk --new=3:0:+512M --typecode=3:0700 -A 3:set:0 -A 3:set:1 --change-name=3:"BOOTFS B" "${device}"

# Partition 4: 12GB EXT4 "ROOTFS A"
sgdisk --new=4:0:+12G --typecode=4:8300 -A 4:set:0 -A 4:set:1 --change-name=4:"ROOTFS A" "${device}"

# Partition 5: 12GB EXT4 "ROOTFS B"
sgdisk --new=5:0:+12G --typecode=5:8300 -A 5:set:0 -A 5:set:1 --change-name=5:"ROOTFS B" "${device}"

# Partition 6: Remaining space EXT4 "DATA"
sgdisk --new=6:0:0 --typecode=6:8300 -A 6:set:0 -A 6:set:1 --change-name=6:"DATA" "${device}"

sgdisk --verify "${device}"

# Inform kernel of partition table changes
partprobe "${device}"

# Format partitions
mkfs.vfat -F12 "${device}1" -n "AUTOBOOT"
mkfs.vfat -F32 "${device}2" -n "BOOTFS A"
mkfs.vfat -F32 "${device}3" -n "BOOTFS B"
wipefs -a "${device}4"
mkfs.ext4 -L "ROOTFS A" "${device}4"
wipefs -a "${device}5"
mkfs.ext4 -L "ROOTFS B" "${device}5"
wipefs -a "${device}6"
mkfs.ext4 -L "DATA" "${device}6"

# decompress
if [ ! -f ${img} ]; then
    xz -d -k ${file}
fi

# read image file as block device
LOOPDEV=$(losetup --find --partscan --show "${img}")
if [ -z "${LOOPDEV}" ]; then
    echo "Failed to setup loop device"
    exit 1
fi

# mount bootfs
mpbootfs=$(mktemp -d)
mount "${LOOPDEV}p1" "${mpbootfs}"

# mount rootfs
mprootfs=$(mktemp -d)
mount "${LOOPDEV}p2" "${mprootfs}"

# part 1 AUTOBOOT
mp1=$(mktemp -d)
mount "${device}1" "$mp1"
cp autoboot.ini "$mp1/autoboot.txt"

# part 2 BOOTFS A
mp2=$(mktemp -d)
mount "${device}2" "$mp2"
rsync -a --info=progress2 "${mpbootfs}/" "${mp2}/"
mv "${mp2}/user-data" "${mp2}/user-data.orig"
cp user-data.yaml "${mp2}/user-data"

# part 3 BOOTFS B
mp3=$(mktemp -d)
mount "${device}3" "$mp3"
rsync -a --info=progress2 "${mpbootfs}/" "${mp3}/"
mv "${mp3}/user-data" "${mp3}/user-data.orig"
cp user-data.yaml "${mp3}/user-data"

# part 4 ROOTFS A
mp4=$(mktemp -d)
mount "${device}4" "$mp4"
rsync -aHAX --filter='-x security.selinux' --info=progress2 "${mprootfs}/" "${mp4}/"

# part 5 ROOTFS B
mp5=$(mktemp -d)
mount "${device}5" "$mp5"
rsync -aHAX --filter='-x security.selinux' --info=progress2 "${mprootfs}/" "${mp5}/"

# mount part 6 DATA
mp6=$(mktemp -d)
mount "${device}6" "${mp6}"

./update-mountpoints.js "${LOOPDEV}" "${device}"

sync

./umount.js "${device}"

# undo
./umount.js "${LOOPDEV}"
losetup --detach "${LOOPDEV}"
