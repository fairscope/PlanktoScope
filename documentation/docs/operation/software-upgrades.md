# Software Reset & Upgrades

Your PlanktoScope's embedded Raspberry Pi computer has a PlanktoScope-specific operating system (the _PlanktoScope OS_) with software for operating your PlanktoScope. If you purchased a PlanktoScope, then the SD card you received with your PlanktoScope already includes a particular release of the PlanktoScope OS; if you assembled your own PlanktoScope, then you installed some release of the PlanktoScope OS following the [standard software installation guide](../setup/software/standard-install.md). This guide provides information to help you either reset the software installed on your PlanktoScope or change to a different (newer or older) release of the PlanktoScope OS.

The PlanktoScope project aims to keep improving the PlanktoScope software by fixing problems and making the software simpler and easier to use, [releasing](../reference/software/release-process.md) a new version of the software at least once (or hopefully twice) each year. At the same time, we aim to keep the software compatible with all previous officially-released versions of the PlanktoScope hardware. For this reason, we strongly recommend everyone to keep their PlanktoScopes updated to run the latest stable release of the PlanktoScope software; and the PlanktoScope documentation will only support the latest stable release. You can always find the latest stable release at <https://github.com/fairscope/PlanktoScope/releases/latest>, which will redirect you to a web page for a specific release.

All URLs in this guide are written assuming you access your PlanktoScope using [planktoscope.local](http://planktoscope.local) as the domain name; if you need to use a [different domain name](./index.md#access-your-planktoscopes-software), you should substitute that domain name into the links on this page.

## Back up your data & settings

Before you reset/upgrade/downgrade the software installed on your PlanktoScope, you may want to back up any important data and settings on your PlanktoScope. We recommend everyone to take the following actions:

- You should use the dataset file browser (accessible via a link on our PlanktoScope's landing page, or via [the Node-RED dashboard's Gallery page](./user-interface.md#gallery)) to download any data you don't want to lose.
- You should write down the white balance gains you have calibrated on [the Node-RED dashboard's Optic Configuration page](./user-interface.md#optic-configuration), as those values may be lost depending on how you reset or upgrade/downgrade the PlanktoScope OS.
- You should write down the hardware settings and calibrations you see on [the Node-RED dashboard's Hardware Settings page](./user-interface.md#hardware-settings), as those values may be lost depending on how you reset or upgrade/downgrade the PlanktoScope OS.

Advanced users may also want to take the following actions, depending on what changes they have made:

- If you don't want to write down your white balance gains and hardware settings/calibrations, you can instead back up your PlanktoScope's hardware settings file, which is saved at `/opt/PlanktoScope/hardware.json`, for example in the file browser at <http://planktoscope.local/admin/fs/files/opt/PlanktoScope/> . This file includes some hidden settings not exposed in the PlanktoScope's Node-RED dashboard - so if you have changed any such settings by editing this file, then you may want to back up this file.

## Reset the PlanktoScope OS

This involves completely wiping your SD card and resetting everything by re-flashing your PlanktoScope's SD card. You can do this by writing an SD card image to the SD card, following the instructions in our [standard software installation guide](../setup/software/standard-install.md). If you want to reset to the same release of the PlanktoScope as what you were originally using, you can check the release's version number in the "Software Version" field of the "Information" panel in [the Node-RED dashboard's System Monitoring page](./user-interface.md#system-monitoring); then you should download an SD card image for the corresponding release (as described in the software installation guide). When you re-flash the SD card, it will lose all data and non-default settings mentioned in [the section of this guide on backing up your data & settings](#back-up-your-data-settings).

## Upgrade/downgrade the PlanktoScope OS

Currently, to upgrade or downgrade your PlanktoScope to some other release of the PlanktoScope OS, we recommend flashing a new SD card with an SD card image for that release of the PlanktoScope OS, following the instructions in our [standard software installation guide](../setup/software/standard-install.md). That way, you can always swap back to your previous SD card if needed. If you only have one SD card, you can re-flash that SD card with the SD card image you want to run - but you will lose all your data and settings, unless you previously [backed them up](#back-up-your-data-settings).

## Restore your data & settings

If you reset/upgraded/downgraded the PlanktoScope OS by re-flashing your SD card, then you can restore your [backed-up data & settings](#back-up-your-data-settings) by re-uploading your backup files to their respective locations and then rebooting your PlanktoScope.
