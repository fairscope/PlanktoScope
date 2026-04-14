# Building PlanktoScope OS image

This folder contains scripts and documentation to build the PlanktoScope OS image.

The scripts should work on standard Linux installations, in case of doubt use Raspberry Pi OS.

Make sure to run `just` first.

## Status

This process was previously automated but was causing too much friction. See https://github.com/fairscope/PlanktoScope/issues/730

## Flash Raspberry Pi OS

⚠️ Make sure to replace /dev/device with the correct path

```sh
cd image
sudo ./make-raspios-disk.sh /dev/device
```

This is a CLI equivalent of using RPI Imager.

* Erases the disk
* Writes Raspberry Pi OS to the disk
* Sets `pi:copepode` as default username/password
* Enables password authentication SSH

## Run the setup script

Boot the PlanktoScope into the newly flashed disk and connect Ethernet.

Find its IP address using your router dashboard or `nmap 123 192.168.1.0/24`.

```sh
ssh pi@192.168.1.xxx
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/fairscope/PlanktoScope/HEAD/os/setup.sh)"
# After the script ran succesfully
sudo poweroff
```

## Create the image

Plug the disk into your computer and run

```sh
cd image
sudo ./make-planktoscope-disk.sh /dev/device pkos
```

This will create a file pkos.img.xz which you can rename and upload.

# Partioning

Here is the state when booting on slot A

```sh
$ lsblk --output=PATH,PARTUUID,LABEL,PARTLABEL,MOUNTPOINT,FSTYPE,SIZE,FSUSE% /dev/nvme0n1
PATH           PARTUUID                             LABEL    PARTLABEL MOUNTPOINT       FSTYPE   SIZE FSUSE%
/dev/nvme0n1                                                                                   238.5G
/dev/nvme0n1p1 c25513db-e90b-4a94-828a-b55b47c211ab AUTOBOOT AUTOBOOT  /boot/bootloader vfat       8M     0%
/dev/nvme0n1p2 249d696b-e06c-4823-82e7-dea61f53574f BOOTFS A BOOTFS A  /boot/firmware   vfat     512M    13%
/dev/nvme0n1p3 df7f4dc3-5c86-4903-b2c0-28a97111c6f8 BOOTFS B BOOTFS B                   vfat     512M 
/dev/nvme0n1p4 2e37401a-6bd0-4bdd-ab89-4d2879637afe ROOTFS A ROOTFS A  /                ext4      12G    39%
/dev/nvme0n1p5 f5709873-a0f7-4cac-8869-96b32b36cb03 ROOTFS B ROOTFS B                   ext4      12G 
/dev/nvme0n1p6 1c14ee2b-a7cd-4322-a1f7-8a48f0b69b44 DATA     DATA      /home/pi/data    ext4   213.5G     7%
```

And here is compared when booting on slot B

```sh
$ lsblk --output=PATH,PARTUUID,LABEL,PARTLABEL,MOUNTPOINT,FSTYPE,SIZE,FSUSE% /dev/nvme0n1
PATH           PARTUUID                             LABEL    PARTLABEL MOUNTPOINT       FSTYPE   SIZE FSUSE%
/dev/nvme0n1                                                                                   238.5G
/dev/nvme0n1p1 c25513db-e90b-4a94-828a-b55b47c211ab AUTOBOOT AUTOBOOT  /boot/bootloader vfat       8M     0%
/dev/nvme0n1p2 249d696b-e06c-4823-82e7-dea61f53574f BOOTFS A BOOTFS A                   vfat     512M 
/dev/nvme0n1p3 df7f4dc3-5c86-4903-b2c0-28a97111c6f8 BOOTFS B BOOTFS B  /boot/firmware   vfat     512M    13%
/dev/nvme0n1p4 2e37401a-6bd0-4bdd-ab89-4d2879637afe ROOTFS A ROOTFS A                   ext4      12G 
/dev/nvme0n1p5 f5709873-a0f7-4cac-8869-96b32b36cb03 ROOTFS B ROOTFS B  /                ext4      12G    39%
/dev/nvme0n1p6 1c14ee2b-a7cd-4322-a1f7-8a48f0b69b44 DATA     DATA      /home/pi/data    ext4   213.5G     7%
```

Note:

* `BOOTFS A` and `ROOTFS A` have been "replaced" with `BOOTFS A` and `ROOTFS B`
* `AUTOBOOT` and `DATA` partitions stay the same

Processus (booted SLOT A):

Rauc starts, it detects which slot was booted using the `root` argument of `/proc/cmdline` which is carried over from `/boot/firmware/cmdline.txt`

`rauc install update-2015.04-1.raucb`

immediately calls `set-state B bad` because we are writing to it so it becomes unbootable
