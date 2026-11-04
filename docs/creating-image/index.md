# Creating a new image

You need to have a rauc bundle. See [Creating a bundle](../creating-update)

### Install

1. Boot to slot A
2. Install bundle to slot B
5. Boot to slot B
7. Install bundle to slot A

### Prepare device

On the live system

```sh
sudo NODE_DEBUG=execa ./prepare-data.js
sudo poweroff
```

### Create image

On a system with the block device

```sh
sudo apt install bmaptool zerofree
version=2026.0.0
device=/dev/device
sudo zerofree -v ${device}p4 # ROOT_A
sudo zerofree -v ${device}p5 # ROOT_B
sudo zerofree -v ${device}p6 # DATA
sudo dd bs=4M if=${device} status=progress conv=sparse,fsync of=PlanktoScopeOS-${version}.img
bmaptool create PlanktoScopeOS-${version}.img --output PlanktoScopeOS-${version}.img.bmap
xz -T0 -9e --keep PlanktoScopeOS-${version}.img
```

The resulting files are `PlanktoScopeOS-$version.sparse.img.xz` and `PlanktoScopeOS-$version.sparse.img.bmap`.

<!--
also an interesting option from libguestfs-tools
virt-sparsify --in-place PlanktoScopeOS-${version}.img

faster compression
# zstd -T0 -10 --keep PlanktoScopeOS-${version}.img
-->

### Write the image

On a system with the block device

```sh
sudo apt install bmaptool
version=2026.0.0
device=/dev/device
sudo bmaptool copy PlanktoScopeOS-$version.img.xz $device --bmap PlanktoScopeOS-$version.img.bmap
```

See also [Flasher](https://github.com/fairscope/Flasher).
