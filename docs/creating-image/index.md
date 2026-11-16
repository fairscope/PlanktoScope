# Creating a new image

You need to have a rauc bundle. See [Creating a bundle](../creating-update)

### Install

1. Boot to slot A
2. Install bundle to slot B
3. Boot to slot B
4. Install bundle to slot A
5. Boot to Slot A

### Prepare device

On the live system

```sh
sudo NODE_DEBUG=execa /opt/PlanktoScope/os/image/create-image.js
sudo poweroff
```

### Create image

On a system with the block device

```sh
version=2026.0.0
device=/dev/device
sudo NODE_DEBUG=execa "$device" PlanktoScopeOS-"$version".img
```

The resulting files are `PlanktoScopeOS-$version.img.xz` and `PlanktoScopeOS-$version.img.bmap`.

### Write the image

On a system with the block device

```sh
version=2026.0.0
device=/dev/device
sudo bmaptool copy PlanktoScopeOS-"$version".img.xz "$device" --bmap PlanktoScopeOS-"$version".img.bmap
```

Please remember that after flashing; running `/factory` is necessary for operating.

See also [Flasher](https://github.com/fairscope/Flasher).
