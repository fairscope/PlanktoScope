# Image

Since PlanktoScope OS v2026, we use [RAUC](../../os/rauc) to create and install software updates.
The PlanktoScope contains 2 slots; A and B; each able to host the entirety of the operating system.

This document list all the steps to create a PlanktoScope OS disk and image from scratch. You can skip stages depending on what you have available and what whish to achieve.

- [Stage 0 - Create disk](#stage-0---create-disk)
- [Stage 1 - Create Raspberry Pi OS bundle](#stage-1---create-raspberry-pi-os-bundle)
- [Stage 2 - Create PlanktoScope OS bundle](#stage-2---create-planktoscope-os-bundle)
- [Stage 3 - Create image file](#stage-3---create-image-file)
- [Stage 4 - Flash disk with image](#stage-4---flash-disk-with-image)
- [Stage 5 - Publish update](#stage-5---publish-update)

## Stage 0 - Create disk

This stage formats a disk with the correct partition layout and install Raspberry Pi OS on A and B slots.
This is only needed if you don't have a disk with the right partition layout.

You will need to run this from a Raspberry Pi with the disk connected.

```sh
# If you don't have /opt/PlanktoScope
sudo install -d -o "$USER" -g "$USER" /opt/PlanktoScope && git clone https://github.com/fairscope/PlanktoScope.git /opt/PlanktoScope
cd /opt/PlanktoScope/os/image
just setup-dev

# List disk devices and copy appropriate device "PATH"
lsblk -d -o +path,ID,model
# Run the script ⚠️ it will erase everything on the device
sudo NODE_DEBUG=execa ./make-disk.js <DEVICEPATH>
```

See [os/image]([../../os/image) for details.

You can now install the disk in a PlanktoScope.

## Stage 1 - Create Raspberry Pi OS bundle

This stage creates a Raspberry Pi OS bundle. It is only needed if you don't have an updated Raspberry Pi OS bundle. See [RPIOS.env](../../os/RPIOS.env).

The Raspberry Pi OS bundle serves as "runtime" for PlanktoScope software.

```sh
# Install the disk in the PlanktoScope
# Start PlanktoScope on slot A

# SSH
ssh pi@xxx

# Install PlanktoScope software
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/FairScope/PlanktoScope/HEAD/os/setup.sh)"

# Create bundle
sudo NODE_DEBUG=execa pkos create-rpios-bundle
# It will display the path of the raucb file

# From your computer; download the file
scp pi@xxx:/data/tmp/PlanktoScopeOS-rpios-yyyy-mm-dd.raucb .
```

## Stage 2 - Create PlanktoScope OS bundle

This stage creates a Rauc bundle file that can be used for updating PlanktoScope or creating a disk image file.

```sh
# Start PlanktoScope on slot A

# From your computer; send RPIOS bundle to the PlanktoScope (if missing)
scp PlanktoScopeOS-rpios-yyyy-mm-dd.raucb pi@xxx:/data/tmp

# SSH
ssh pi@xxx

# Install Raspberry Pi OS bundle to slot B
rauc install /data/tmp/PlanktoScopeOS-rpios-yyyy-mm-dd.raucb

# Reboot to slot B
sudo pkos reboot B

# Install PlanktoScope software to slot B
# This will download and install from `main` branch
# If you want something else clone to `/opt/PlanktoScope` and run `/opt/PlanktoScope/os/setup.sh`
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/FairScope/PlanktoScope/HEAD/os/setup.sh)"
# Optional but it is recommended to create a release git tag
# git tag v2026.x.x
# git push -u origin v2026.x.x
sudo reboot

# Run prepare scripts
sudo NODE_DEBUG=execa pkos prepare

# Reboot to slot A
sudo pkos reboot A

# SSH
ssh pi@xxx

# Create bundle
sudo NODE_DEBUG=execa pkos create-bundle /dev/nvme0n1 B 2026.x.x
# It will display the path of the raucb file

# From your computer; download the file
scp pi@xxx:/data/tmp/PlanktoScopeOS-2026.x.x.raucb .
```

## Stage 3 - Create image file

This stage creates a full disk image PlanktoScope OS file that can be used for flashing disks. You need a disk created with [Stage 0 - Create disk](#stage-0---create-disk) - not flashed with an image file so that the `DATA` partition is 5GB instead of having been expanded.

```sh
# Start PlanktoScope on slot A
ssh pi@xxx

# From your computer; send PlanktoScope OS bundle to the PlanktoScope (if missing)
scp PlanktoScopeOS-2026.x.x.raucb pi@xxx:/data/tmp

# Install bundle to slot B
rauc install /data/tmp/PlanktoScopeOS-2026.x.x.raucb

# Reboot to slot B
sudo pkos reboot B
ssh pi@xxx

# Install bundle to slot A
rauc install /data/tmp/PlanktoScopeOS-2026.x.x.raucb

# Reboot to slot A
sudo pkos reboot A
ssh pi@xxx

# Prepare /data for image
sudo NODE_DEBUG=execa /opt/PlanktoScope/os/image/prepare-data.js

# Poweroff
sudo poweroff
```

Plug the disk on a NVMe or SDCard reader.

```sh
# Create the disk image file
version=2026.x.x
device=/dev/device # Find with lsblk -d -o +path,ID,model
sudo NODE_DEBUG=execa "$device" PlanktoScopeOS-"$version".img
```

The resulting files are `PlanktoScopeOS-$version.img.xz` and `PlanktoScopeOS-$version.img.bmap`.

## Stage 4 - Flash disk with image

Plug the disk on a NVMe or SDCard reader.

```sh
version=2026.x.x
device=/dev/device # Find with lsblk -d -o +path,ID,model
sudo bmaptool copy PlanktoScopeOS-"$version".img.xz "$device" --bmap PlanktoScopeOS-"$version".img.bmap
# or
xzcat PlanktoScopeOS-"$version".img.xz | sudo dd of="$device" bs=4M conv=fsync status=progress
```

Please remember that after flashing; running `/factory` is necessary for operating.

## Stage 5 - Publish update

You should have the following files:

* `PlanktoScopeOS-rpios-yyyy-mm-dd.raucb`
* `PlanktoScopeOS-"$version".raucb`
* `PlanktoScopeOS-"$version".img.bmap`
* `PlanktoScopeOS-"$version".img.xz`

Create a GitHub release and attach the 4 files to it.

Copy the download link to the `PlanktoScopeOS-"$version".raucb` file and update [backend](https://github.com/fairscope/backend/blob/main/server.js) with it. 

On push, our [coolify backend instance](https://coolify.backend.eplankton.org/project/tyhdrab66bj0s4kzj78lhkbz/environment/yk2pftegwdcdlhlpibefvzzr/application/xxrfxrlhxsxzxxamipdd1zbw/deployment) will automatically re-deploy and PlanktoScopes will be able to update with the new bundle.
