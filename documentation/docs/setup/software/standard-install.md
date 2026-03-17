# Standard Installation

![easy install](../../images/software/IMG_1532.jpg)

This page provides instructions for installing the most recent standard version of the PlanktoScope OS on a PlanktoScope.

## Set up the SD card

If you purchased a fully-assembled PlanktoScope or a DIY-assembly PlanktoScope kit from FairScope which includes a microSD card, then the SD card is already set up with the PlanktoScope OS, and you should skip to [the next step](#insert-the-sd-card-into-the-planktoscope).

### Prerequisites

In order to complete this step, you will need all of the following:

1. A microSD card for your Raspberry Pi.
2. A separate computer which can flash SD card images to your microSD card.

### Download the PlanktoScope software SD card image

For ease of setup, we distribute the PlanktoScope OS as SD card image files. You can download the latest release from the [stable releases page](https://github.com/fairscope/PlanktoScope/releases?q=prerelease%3Afalse+draft%3Afalse&expanded=true) for the PlanktoScope project on GitHub (if you are experienced with the PlanktoScope software, you can also try the latest alpha or beta testing releases on the [full releases page](https://github.com/fairscope/PlanktoScope/releases?q=draft%3Afalse&expanded=true)). Each released version of the PlanktoScope OS has downloadable SD card images under the "Assets" dropdown, which has multiple SD card image files corresponding to different types of PlanktoScope hardware; for information about how to select the appropriate SD card image for your PlanktoScope hardware, refer to the ["Hardware configurations"](index.md#hardware-configurations) section of the software setup overview.

### Write the image to the SD card

To write the image file to your microSD card:

1. Download, install, and start the latest version of the [Raspberry Pi Imager](https://www.raspberrypi.com/software/).
2. Plug your microSD card into your computer; you may need to use a microSD-to-SD-card adapter, and/or an SD-card-to-USB adapter.
3. Press the "Choose Device" button. Select "No filtering" from the menu. It actually doesn't matter what you select here.
4. Press the "Choose OS" button. Select "Use custom" from the menu (this is why it doesn't matter what you selected in the "Choose Device" menu). In the file dialog, open the PlanktoScope SD card image file you downloaded in the previous section of this setup guide.
5. Press the "Choose Storage" button. Select your SD card from the menu.
6. Press the "Next" button. A pop-up dialog should appear asking if you would like to customize the OS. You should probably press the "No" button unless you are already experienced with the PlanktoScope software, because most of the settings inside don't matter to typical users of the PlanktoScope software, and because it's possible to break the software with incorrect settings.
7. A pop-up dialog should appear asking you to confirm whether you selected the correct SD card and want to wipe all data on the SD card in order to write the PlanktoScope SD card image to your SD card. If you are ready, press the "Yes" button.
8. The Raspberry Pi Imager will begin overwriting your SD card with the PlanktoScope SD card image. This will take a while to finish.

Once flashing is complete, unmount the SD card and remove it from the computer.

## Insert the SD card into the PlanktoScope

Insert the microSD card into the Raspberry Pi computer installed in your PlanktoScope.

## Connect to the PlanktoScope

Power on your PlanktoScope, and wait for it to start up. Note that it may take a minute to start up. Once it has finished starting up, its internal Raspberry Pi computer should create a new isolated Wi-Fi network (which we call the PlanktoScope's _Wi-Fi hotspot_) whose name starts with the word `PlanktoScope ` followed by your PlanktoScope's _machine name_, a unique randomly-generated name; for example, if your PlanktoScope's machine name is `sponge-bob`, then the Wi-Fi network will be named `PlanktoScope sponge-bob`. The password of this Wi-Fi network is `copepode`.

!!! info

    You will not be able to access the PlanktoScope's graphical user interface by plugging in a display to the Raspberry Pi. This is because the SD card image we provide does not include a graphical desktop or web browser, in order to keep the SD card image file smaller and to keep the PlanktoScope's Raspberry Pi running more efficiently.

Once your PlanktoScope has created its Wi-Fi hotspot, you can connect your computer (or phone/tablet/etc.) directly to the PlanktoScope - either through its Wi-Fi hotspot or through an Ethernet cable directly to the PlanktoScope's Ethernet port. Afterwards, you can open a web browser on your computer to access the PlanktoScope's graphical user interface at one of the following URLs (try them in the following order, and just use the first one which works):

- <http://planktoscope.local> (this should work unless you're on a computer or web browser without mDNS support; notably, older versions of Android did not support mDNS, and web browsers installed on Linux computers via Flatpak [do not yet support mDNS](https://github.com/flatpak/xdg-desktop-portal/discussions/1365))
- <http://planktoscope-{machine-name}.local> (this should work unless you're on a computer or web browser without mDNS support)
- <http://192.168.4.1> (this should always work on computers connected to the PlanktoScope's Wi-Fi hotspot, unless your computer is also connected to some other device meant to be accessed with that URL)

## Next steps

Now that you have installed the software and accessed the PlanktoScope software's user interface from your web browser, you should proceed to our guide for [configuring your PlanktoScope](config.md).
