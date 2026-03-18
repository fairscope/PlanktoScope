# Building PlanktoScope OS image

This folder contains scripts and documentation to build the PlanktoScope OS image.

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
