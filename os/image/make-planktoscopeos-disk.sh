#!/bin/bash -eux

device=$1
name=$2
file=$name.img

# save raspios
dd bs=1M if="$device" status=progress conv=fdatasync of="$file"

# shrink
pishrink.sh -Za "$file"

# compress
# xz -T0 -9 -k $file
