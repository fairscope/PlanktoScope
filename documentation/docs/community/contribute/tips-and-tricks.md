# Tips and tricks

This page provides useful snippets and how-tos while developing software for the PlanktoScope.

!!! warning

    This document is meant for PlanktoScope developers. Proceed with care.

## Building the OS

You will have to flash [2026-04-21-raspios-trixie-arm64-lite.img.xz](https://downloads.raspberrypi.com/raspios_lite_arm64/images/raspios_lite_arm64-2026-04-21/).

⚠️ No other version is supported. ⚠️

* For PlanktoScope v2.6 flash to SDCard
* For PlanktoScope v3.0 flash to SSD (from SDCard or with USB NVME adapter)

You can use `Raspberry Pi Imager` (v2) -> `OS` -> `Use custom`

1. Wait for the image to be written
2. Re-insert the SDCard
3. Open the `bootfs` partition
4. Replace the content of the file `user-data` with:

```yaml
#cloud-config

users:
  - name: pi
    plain_text_passwd: copepode
    lock_passwd: false

ssh_pwauth: true
enable_ssh: true
```

Then boot into Raspberry Pi OS and type the following commands using SSH

```sh
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/FairScope/PlanktoScope/HEAD/os/setup.sh)"
# After the script ran succesfully
sudo reboot
```

After the PlanktoScope has rebooted you can open its URL in your browser.

PlanktoScope OS is ready.

## Updating the OS

Type the following commands

```sh
cd /home/pi/PlanktoScope
just update
# don't forget to copy default configs if needed/wanted
# cp default-configs/v3.0.hardware.json hardware.json
# cp default-configs/v3.0.config.json config.json

# After the script ran succesfully
sudo reboot
```

PlanktoScope OS is updated.

## Graphical UI

To install the graphical desktop similar to what you find on the desktop edition of Raspberry Pi OS proceed as following:

<!--https://www.raspberrypi.com/news/trixie-the-new-version-of-raspberry-pi-os/ -->

```sh
sudo apt install rpd-wayland-core rpd-theme rpd-preferences rpd-applications rpd-utilities rpd-developer rpd-graphics rpd-wayland-extras
# Change the boot option
sudo raspi-config # System Options -> Boot -> Desktop GUI
sudo reboot
```

## Development Environment

To setup the recommended development environment, run the following commands.

Make sure to replace `$planktoscope` with your PlanktoScope hostname, eg. `planktoscope-sponge-bob`

<details>
    <summary>On your computer</summary>

```sh
# Create an SSH key for the PlanktoScope specifically
ssh-keygen -t ed25519 -C "pi@$planktoscope" -f ~/.ssh/$planktoscope
# Make the SSH key accepted by the PlanktoScope
ssh-copy-id -i ~/.ssh/$planktoscope.pub pi@$planktoscope
# Add your keys to your SSH agent
ssh-add -k
```

```sh
# Add the following to ~/.ssh/config
Host $planktoscope
  # https://docs.github.com/en/authentication/connecting-to-github-with-ssh/using-ssh-agent-forwarding
  ForwardAgent yes
  User pi
  IdentityFile ~/.ssh/$planktoscope
```

</details>

You can now SSH into your PlanktoScope without username / password (using `ssh $planktoscope`).

<details>
    <summary>On the PlanktoScope</summary>

```sh
cd ~/PlanktoScope
just developer-mode
git checkout main
git status
```

</details>

We recommend developping directly from the PlanktoScope using [Visual Studio Code and the Remote - SSH extension](https://code.visualstudio.com/docs/remote/ssh) or [Zed - Remote Development](https://zed.dev/docs/remote-development). Use `$planktoscope` as the host to connect to and open the `/home/pi/PlanktoScope` directory.

## Connect to router

The supported way to connect the PlanktoScope to a router is with an Ethernet cable.
If that is not possible you may try the following:

```sh
nmcli connection down wlan0-hotspot
nmcli device wifi list
nmcli device wifi connect "<SSID>" --ask
```

Your PlanktoScope should be accessible via its hostname which you can retrieve from the PlanktoScope with `hostnamectl`

You can then ssh into it with `ssh://pi@planktoscope-sponge-bob`

And access the UI with http://planktoscope-sponge-bob/

If that doesn't work, type `nmap -sn 192.168.1.0/24` from your computer to find the PlanktoScope hostname and/or ip address.

## Offline access

When network is not available you have several options for debugging

- Plug-in a keyboard and display (needs micro HDMI adapter)
- [Connect a serial cable](https://www.jeffgeerling.com/blog/2021/attaching-raspberry-pis-serial-console-uart-debugging)
- Use [NanoKVM USB](https://wiki.sipeed.com/hardware/en/kvm/NanoKVM_USB/introduction.html) (no need for network)
- Use [JetKVM](https://jetkvm.com/) (local network needed)

## Backup and Restore SD Card

Plug the SD card into your computer.

`/dev/device` refers to the path of the SD card device/disk. You will need to adjust it. Use `diskutil list` on macOS and `fdisk --list` on Linux.

```sh
# backup whole SD card onto an image file on your computer
sudo dd bs=1M if=/dev/device status=progress conv=fdatasync | xz > sdcard.img.xz
```

```sh
# restore an image file from your computer onto the SD card
xzcat sdcard.img.xz | sudo dd bs=1M of=/dev/device status=progress conv=fdatasync
```

See also the operating guide [SD Card Cloning](../../operation/clone-sd.md).

## Working with GPIOs on the CLI

https://lloydrochester.com/post/hardware/libgpiod-intro-rpi/

## Documentation quick setup

This is a quick setup guide. See also

- [documentation README](https://github.com/fairscope/PlanktoScope/blob/main/documentation/README.md)
- [Writing Documentation](./documentation.md)

Install dependencies:

<details>
    <summary>Windows</summary>

Start by [installing WSL (Ubuntu)](https://learn.microsoft.com/en-us/windows/wsl/install#install-wsl-command)

Because of a small incompatibilty between Windows and Linux; we recommend cloning the repo "in WSL" but if you prefer keeping your git clone "in Windows", here are other options:

- [Git line endings](https://learn.microsoft.com/en-us/windows/wsl/tutorials/wsl-git#git-line-endings)
- [Visual Studio Code WSL extension](https://code.visualstudio.com/docs/remote/wsl)

Then follow the Ubuntu instructions below.

</details>

<details>
    <summary>Ubuntu</summary>

```shell
sudo apt update
sudo apt install uv
cd documentation
uv sync
```

</details>

<details>
    <summary>Fedora</summary>

```shell
sudo dnf install uv
cd documentation
uv sync
```

</details>

Run live previewer:

```sh
cd documentation
uv run poe preview
```

Visit [`http://localhost:8000`](http://localhost:8000) to see local changes.
