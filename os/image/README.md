# Building PlanktoScope OS image

This folder contains scripts and documentation to build the PlanktoScope OS image.

The scripts should work on standard Linux installations, in case of doubt use Raspberry Pi OS.

Make sure to run `just` first.

## How does it work

This creates a disk with an A/B partition scheme bootstrapped with Raspberry Pi OS.

Tested with:

- Raspberry Pi 4 and 5
- SD card (`/dev/mmcblk0`)
- NVMe `/dev/nvme0n1`)

The partition table is as such:

| PATH                    | PARTLABEL  | MOUNTPOINT  | FSTYPE | FSSIZE              |
| ----------------------- | ---------- | ----------- | ------ | ------------------- |
| /dev/`${device_node}`p1 | BOOTLOADER | /bootloader | vfat   | 8M                  |
| /dev/`${device_node}`p2 | FIRMWARE_A |             | vfat   | 256M                |
| /dev/`${device_node}`p3 | FIRMWARE_B |             | vfat   | 256M                |
| /dev/`${device_node}`p4 | ROOT_A     |             | ext4   | 10G                 |
| /dev/`${device_node}`p5 | ROOT_B     |             | ext4   | 10G                 |
| /dev/`${device_node}`p6 | DATA       | /data       | ext4   | rest of avail space |

The following documentation assumes you are familiar with the traditional Raspberry Pi OS partitioning (`bootfs` and `rootfs`) and boot flow.

---

`BOOTLOADER` only contains [`autoboot.txt`](https://www.raspberrypi.com/documentation/computers/config_txt.html#autoboot-txt) (to specify boot partition) and [cloud-init configuration files](https://www.raspberrypi.com/news/cloud-init-on-raspberry-pi-os/) which normally live in `bootfs`.

---

`FIRMWARE_A` and `FIRMWARE_B` are equivalent to RPI OS `bootfs`. `cmdline.txt` is replaced with `cmdline-A.txt` and `cmdline-B.txt`. `config.txt` is updated to choose the appropriate cmdline file based on the boot partition. They are only needed by the Raspberry Pi firmware and as such, they are not mounted after boot.

---

`ROOT_A` and `ROOT_B` are equivalent to RPI OS `rootfs` with minor changes:

- Update cloud-init to read configuration from `BOOTLOADER`
- A/B compatible `/etc/fstab`
- 

---

The A/B boot flow of the Raspberry Pi is unfortunaly not well documented at the time of writing this so we'll explain in detail here what happens.

The Raspberry Pi powers on.
It checks for the file

`BOOTLOADER` contains the partition

Each bootname (A and B) contains a `firmware` and a `root` slot

## Flash Raspberry Pi OS

⚠️ Make sure to replace /dev/device with the correct path

```sh
cd image
sudo ./make-raspios-disk.sh /dev/device
```

This is a CLI equivalent of using RPI Imager.

- Erases the disk
- Writes Raspberry Pi OS to the disk
- Sets `pi:copepode` as default username/password
- Enables password authentication SSH

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
