# Building PlanktoScope OS image

This folder contains scripts and documentation to build the PlanktoScope OS image.

The scripts should work on standard Linux installations, in case of doubt use Raspberry Pi OS.

## How to use

### Bootstrap Raspberry Pi OS

This creates a disk with an A/B partition scheme bootstrapped with Raspberry Pi OS.

Tested with:

- Raspberry Pi 4 and 5
- SD card (`/dev/mmcblk0`)
- NVMe `/dev/nvme0n1`)

```sh
cd PlanktoScope/os/image
just
# List disk devices and copy approrpriate "PATH"
lsblk -d -o +path,ID,model
# Run the script ⚠️ it will erase everything on the device
sudo NODE_DEBUG=execa ./make-disk.js <PATH>
```

You know should have a device with the partition table documented below.

username/password is `pi:copepode`
hostname is `raspberrypi`

Both slots are bootable and contain a Raspberry Pi OS operating system. You can switch between them using

* slot A: `sudo reboot 2`
* slot B: `sudo reboot 3`
* [tryboot](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html#fail-safe-os-updates-tryboot): `sudo reboot '0 tryboot'`

To change the boot partition permanently update `/bootloader/autoboot.txt`. See below how to remount `/bootloader` readwrite.

### Installing PlanktoScope software

Boot the PlanktoScope into the newly flashed disk and connect Ethernet.

Find its IP address using your router dashboard or `nmap 123 192.168.1.0/24`.

```sh
ssh pi@192.168.1.xxx
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/fairscope/PlanktoScope/HEAD/os/setup.sh)"
```

Congratulations, the slot is running PlanktoScope OS.

## How does it work

### Partition table

The partition table is as such:

| device path             | partlabel  | mountpoint when A | mountpoint when B | type | size                |
| ----------------------- | ---------- | ----------------- | ----------------- | ---- | ------------------- |
| /dev/`${device_node}`p1 | BOOTLOADER | /bootloader       | /bootloader       | vfat | 8M                  |
| /dev/`${device_node}`p2 | FIRMWARE_A | /boot/firmware    |                   | vfat | 256M                |
| /dev/`${device_node}`p3 | FIRMWARE_B |                   | /boot/firmware    | vfat | 256M                |
| /dev/`${device_node}`p4 | ROOT_A     | /                 |                   | ext4 | 10G                 |
| /dev/`${device_node}`p5 | ROOT_B     |                   | /                 | ext4 | 10G                 |
| /dev/`${device_node}`p6 | DATA       | /data             | /data             | ext4 | rest of avail space |

The following documentation assumes you are familiar with the traditional Raspberry Pi OS partitions (`bootfs`/`rootfs`) and boot flow.

---

`BOOTLOADER` only contains [`autoboot.txt`](https://www.raspberrypi.com/documentation/computers/config_txt.html#autoboot-txt) (to specify boot partition) and [cloud-init configuration files](https://www.raspberrypi.com/news/cloud-init-on-raspberry-pi-os/) which normally live in `bootfs`.

For safety reasons it is mounted read only. You can edit files with

```sh
# remount readwrite
sudo mount -o remount,rw /bootloader
# update files
sudo nano /bootloader/autoboot.txt
# remount readonly
sudo mount -o remound,ro /bootloader
```

---

`FIRMWARE_A` and `FIRMWARE_B` are equivalent to RPI OS `bootfs`. `cmdline.txt` is replaced with `cmdline-A.txt` and `cmdline-B.txt`. `config.txt` is updated to choose the appropriate cmdline file based on the boot partition.

`/etc/fstab` must be the sames on both `A` and `B` so we cannot use it to mount `/boot/firmware`, instead it is mounted by the `mount-firmware` service.

For safety reasons it is mounted read only. If you wish to use `raspi-config`, update the EEPROM or the kernnel you will have to remount it as such:

```sh
# remount readwrite
sudo mount -o remount,rw /boot/firmware
# make changes, then
# remount readonly
sudo mount -o remound,ro /boot/firmware/
```

---

`ROOT_A` and `ROOT_B` are equivalent to RPI OS `rootfs` with minor changes:

- Update cloud-init to read configuration from `BOOTLOADER`
- A/B compatible `/etc/fstab`
- `/etc/machine-id` is a symlink to `/data/machine-id`

---

`DATA` is a partition shared between A and B.

It includes contains `/home` and `machine-id` and anything else that needs to be shared between `A` and `B`.

---

### Bootflow

Unfortunaly the Raspberry Pi bootflow we use is poorly/sparsly documented but you can ready about it [here](https://waldorf.waveform.org.uk/2025/pull-yourself-up-by-your-bootstraps.html#full-abs), [here](https://www.raspberrypi.com/documentation/computers/config_txt.html#autoboot-txt) and [here](https://bootlin.com/blog/safe-updates-using-rauc-on-raspberry-pi-5/).

Here is a simplified "high level" sequence of what happens:

0. Raspberry Pi powers on
1. EEPROM bootloader opens the first partition `BOOTLOADER` and reads `autoboot.txt`
2. Firmware (GPU) initializes with the partition `FIRMWARE_A|B` defined in `autoboot.txt` (boot or tryboot depending on the state flag)
3. The firmware opens the partition and reads `config.txt` which tells it which `cmdline-A|B.txt` file to use
4. It initializes the Linux kernel using the cmdline arguments and mounts the given `ROOT_A|B` partition
5. systemd reads `/etc/fstab` and mounts accordingly
   - `BOOTLOADER` to `/bootloader` - readonly
   - `DATA` to `/data` - readwrite
   - `DATA/home` to `/home`
6. systemd executes `mount-firmware.service` and `/boot/firmware` becomes available

## Full system image

You need to have a rauc bundle. See [Creating a bundle](../pkos/README.md)

### Install

1. Boot to slot A
2. Install bundle to slot B
5. Boot to slot B
7. Install bundle to slot A

### Prepare device

On the live system

```sh
sudo ./prepare-data.js
sudo poweroff
```

### Create image

On a system with the block device

```sh
sudo apt install libguestfs-tools bmaptool
version=2026.0.0-beta.4
device=/dev/sda99
sudo zerofree ${device}p4 # ROOT_A
sudo zerofree ${device}p5 # ROOT_B
sudo zerofree ${device}p6 # DATA
sudo dd bs=4M if=/dev/${device} status=progress conv=fsync conv=sparse of=PlanktoScopeOS-${version}.img
bmaptool create PlanktoScopeOS-${version}.img --output PlanktoScopeOS-${version}.img.bmap
xz -T0 -9 PlanktoScopeOS-${version}.img
```

The resulting files are `PlanktoScopeOS-$version.sparse.img.xz` and `PlanktoScopeOS-$version.sparse.img.bmap`.

<!--
also an interesting option
virt-sparsify --in-place PlanktoScopeOS-${version}.img
-->

### Write the image

On a system with the block device

```sh
sudo apt install bmaptool
version=2026.0.0-beta.4
sudo bmaptool copy PlanktoScopeOS-$version.img.xz /dev/device --bmap PlanktoScopeOS-$version.img.bmap
```
