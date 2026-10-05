# Changelog

All notable changes to the PlanktoScope's software will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project uses [Calendar Versioning](https://calver.org/) with a `YYYY.minor.patch` scheme
for all releases after `v2.3.0`.
All dates in this file are given in the [UTC time zone](https://en.wikipedia.org/wiki/Coordinated_Universal_Time).

## v2026.0.0 - UNRELEASED

Support for PlanktoScope 2.1 was removed. [More info](https://github.com/fairscope/PlanktoScope/pull/821)

Pump and focus can be used at the same time.

### Highlights

**PlanktoScope v3.0**

The PlanktoScope v3.0 is a new model developed by FairScope with many improvements. PlanktoScope OS v2026 is the first release to support it.

**Dashboard**

A brand new dashboard has been developed. It's made to be much more user friendly without sacrificing professional users. It comes with

* Clearer landing page
* Manual calibration of
  * White balance
  * Lightness
  * Pixel Size
  * Pump Calibration


**High Quality preview**

Thanks to a brew new architecture; the camera preview is now much better quality and allows to zoom in to see finer details.

The resolution of the preview was increased from 800x600 to

* PlanktoScope v2.6: 1440x1080 (3.24x better)
* PlanktoScope v3.0: 2028x1520 (6.4x better)

As a reminder, the PlanktoScope captures images at 4056x3040.

**Simplify naming scheme**

Naming scheme for PlanktoScope has been simplified.

e.g.:

* Machine name `sponge-bob-183` -> `sponge-box`
* Hostname `pkscope-sponge-bob-183` -> `planktoscope-sponge-bob`
* WiFi SSID `pkscope-sponge-bob-183` -> `PlanktoScope sponge-bob`

**Improved networking**

The PlanktoScope access point now uses Wi-Fi 5GHz providing faster and more reliable wireless connection.

The PlanktoScope can now connect to a WiFi access point.

### Changes

#### OS

**New base**

PlanktoScope OS is now based on Rapberry Pi OS 2025-11-24 which is powered by [Debian Trixie](https://www.debian.org/releases/trixie/index.html) 13.2.

**Faster boot**

Thanks to a simplification in background services and setup, the PlanktoScope boots (starts) faster.

**Unified images**

Previously, we built and provided different OS images for each PlanktoScope configuration. The configurations are now all unified under a single operating system image.

**More reliable WiFi**

Previously the PlanktoScope was automatically configured to use US WiFi frequencies. We now prompt the user for their location to choose the correct frequencies.

#### Controller

Occasionally the hardware controller would take too long to start. This is fixed.

The camera preview will no longer fail with "If you see this, there probably is an error either with your camera or with the python service. Please try restarting your machine."

The operating time (the amount of seconds powered on) of the LED is now recorded.

#### Segmenter

**Remove previous mask**

Until now the segmenter removed the previous mask. This behavior was problematic so it has been made optional and is now off by default. [Read more](https://planktoscope.slack.com/archives/C01V5ENKG0M/p1714146253356569).

**Minimum object size**

Previously the PlanktoScope would use the `acq_minimum_mesh` metadata and compare it with the detected objects' "filled area" (area of the region with all the holes filled in).

We have changed this behavior to be configurable and more accurate. On every segmentation you will be able to choose a minimum object size in μm. The segmenter will compare it with the detected objects' [area-equivalent diameter](https://www.bettersizeinstruments.com/learn/bettersize-wiki/what-is-equivalent-spherical-diameter/) (the diameter of a circle with the same area as the region).

## v2025.0.0 - 2025-07-21

### Added

- Add 500µm Capillary flowcell option #667
- (Application: GUI) The landing page now has a link to a new page (actually a filebrowser file viewer) which lists the MAC addresses of all network interfaces, to make it easier to figure out MAC addresses for registering the Raspberry Pi on networks which require such registrations as a requirement for internet access.
- (System: networking) If you plug in a supported USB Wi-Fi dongle into the PlanktoScope, now it will by default automatically create a Wi-Fi hotspot network from that Wi-Fi dongle - regardless of whether the PlanktoScope's internal Wi-Fi module is configured to also create the same Wi-Fi hotspot network or to connect to some external Wi-Fi network. This means that the PlanktoScope now supports creating its own Wi-Fi hotspot while simultaneously being connected to the internet via a Wi-Fi network, if you plug in a USB Wi-Fi dongle.
- (System: networking) If the PlanktoScope is connected to a Wi-Fi network with a captive portal, you should be able to access and proceed through the captive portal from a computer/phone connected to the PlanktoScope.
- (System: networking) Firewalld is now enabled, and default firewall policies are provided (via Forklift) for the `public` and `nm-shared` firewall zones. This means that if you want to access any additional ports besides the ports for programs provided with the standard PlanktoScope OS from other devices, now you must add configurations to open those additional ports, e.g. via drop-in configuration snippets in `/etc/firewalld/zones.d`.
- (Developers) [Tips and Tricks page](https://github.com/fairscope/PlanktoScope/blob/main/documentation/docs/community/contribute/tips-and-tricks.md)
- (System) Enable [CQE](https://www.raspberrypi.com/news/sd-cards-and-bumper/) for significantly faster sdcard speed (Raspberry PI 5 only)
- (System) Enable [SDRAM tuning](https://www.jeffgeerling.com/blog/2024/raspberry-pi-boosts-pi-5-performance-sdram-tuning) improvements for faster processing

### Changed

- (Breaking change; Application: GUI) When you press the "Start Acquisition" button in the Node-RED dashboard, it now automatically adjusts the PlanktoScope's system time to match the time in your web browser (but still in UTC time zone on the PlanktoScope) if the times are different by more than one minute, so that datasets will be created with correct dates in the dataset directory structure.
- (Breaking change; System) The official PlanktoScope OS images are now built on Raspberry Pi OS 12 (bookworm, 2025-05-13) instead of Raspberry Pi OS 11 (bullseye). No support will be given for running the PlanktoScope OS setup scripts on bullseye base images, and the OS setup scripts will not work on bullseye.
- (Application: GUI) The Node-RED dashboard now initializes the Sample page's Dilution Factor field to 1.0, instead of leaving it empty.
- (System: networking) Wi-Fi hotspot behavior and network connection management is now based on NetworkManager, as part of an upgrade to Raspberry Pi OS 12 (bookworm). As part of this change the previous autohotspot service has been removed, as it's redundant with functionality now provided by NetworkManager.
- (Application: backend) The systemd services for running the Python hardware controller have now been renamed/unified into `planktoscope-org.device-backend.controller.service`.
- (Application: backend) Replaced isort, flake8 pylint and pylama with [Ruff](https://docs.astral.sh/ruff/).
- (System) Node-RED is now installed using npm
- (Application: backend) Separate pump and focus threads for `planktoscopehat`
- (System) Change boot order to sdcard, nvme then usb
- (Application: GUI) Configure Node-RED so that flows are now part of the git repository
- (Application: backend) Replace rpi.gpio with gpiozero for `planktoscopehat`
- (Application: backend) The `device-backend` is now part of the main `PlanktoScope` monorepo

### Removed

- (Application: backend) The old raspimjpeg-based imager has now been completely removed, following a deprecation in v2024.0.0-alpha.2.
- (Application: GUI) Various elements of the Node-RED dashboard which were deprecated in v2024.0.0 and in v2024.0.0-alpha.2 have now been removed, including the old USB backup functionality.
- (Application: GUI) Portainer (whose default enablement was deprecated in v2024.0.0-alpha.2) is now disabled by default.
- (System) The `planktoscope-org.init-gpio-steppers.service` systemd service, which has never actually worked correctly, is now disabled by default. If for some reason you want to re-enable it, you can use Forklift to enable the `host/planktoscope/gpio-init` package deployment.
- (System) Support for use of the setup scripts (and PlanktoScope software components) on ARMv7 (32-bit OSes) is removed, following a deprecation in v2024.0.0-beta.0.
- (Application: GUI) GPS support for `planktoscopehat` is removed
- (Application) The setting to invert pump and focus is removed
- (Application: backed) Remove deprecated uuid module
- (System) Remove unsupported and broken RTC support
- (System) Stop building desktop images
- (System: backend) Remove unused display module for `planktoscopehat`
- (System: backend) Remove unsupported Waveshare stepper HAT support
- (System: backend) Remove support for unused second LED
- (System: backend) Remove support for unused PWM LED

### Deprecated

- (Application: GUI) In a future release, the Grafana dashboard will no longer be enabled by default; then it will be an opt-in app deployment (which will require an internet connection for downloading Grafana to enable it in the PlanktoScope OS via Forklift). This change will be made after the upcoming v3 of the Node-RED dashboard fully replaces the Grafana-based metrics dashboard on the Node-RED dashboard's System Monitoring page, removing the need for Grafana.
- (Application: GUI) GPS support for `adafruithat` is now deprecated

### Fixed

- (Application: hardware controller) The ISO value stored in dataset metadata now correctly matches the user-set ISO setting, instead of being a constant scaling of the image gain (which is calculated from the user-set ISO according to a camera model-specific scaling factor). This fixes a regression introduced with v2024.0.0-beta.2.
- (System: networking) `planktoscope.local` and `pkscope.local` should now work on local area networks (i.e. when the PlanktoScope is connected to a router) and not just on direct connections.
- (Application: GUI) The Node-RED dashboard's sample page's "Dilution Factor" input field has been renamed to "Concentration Factor", which is a less misleading name for what that input field actually represents.
- (Application: hardware controller) Error handling of a failure to create a raw image dataset directory (e.g. because the directory already exists, due to a duplicate acquisition ID) now correctly terminates the attempted data acquisition run. This fixes a problem which might be a regression introduced with v2024.0.0-alpha.1.
- (Application: backend) The `/home/pi/data` and `/home/pi/device-backend-logs` are now created with non-`root` user ownership, so that their contents can be managed via an SFTP/SCP connection as the `pi` user. This fixes a regression introduced with v2023.9.0-beta.0.
- (System) The system time is now correctly persisted on the filesystem (in `/etc/fake-hwclock.data`) in a way that the system time should no longer reset back to a previous time in the past between reboots.
- (System) Machine name generation now falls back to the `en_US.UTF-8`-based naming scheme when the OS is set to a non-default locale (i.e. anything other than `en_US.UTF-8`), instead of failing and falling back to `unknown`.
- (System: backend) Previously; the pump would stop when focus is complete, this is now solved.

## v2024.0.0 - 2024-12-25

### Added

- (Application: Documentation) The embedded documentation site now includes a PDF of a draft of v4 of the [protocols.io protocol for PlanktoScope operation](https://www.protocols.io/view/planktoscope-protocol-for-plankton-imaging-bp2l6bq3zgqe).

### Removed

- (Application: Documentation) The embedded documentation site no longer includes links or PDFs for [v2 of the protocols.io protocol for PlanktoScope operation](https://www.protocols.io/view/planktoscope-protocol-for-plankton-imaging-bp2l6bq3zgqe/v1) and [v3 of the protocols.io protocol for PlanktoScope operation](https://www.protocols.io/view/planktoscope-protocol-for-plankton-imaging-bp2l6bq3zgqe/v3).

### Deprecated

- (Application: GUI) The following elements of the Node-RED dashboard's "Optic Configuration" tab will be removed in a future release (probably the next major release): "objective lens aperture", "magnification", "pixel resolution", "smallest cells to explore", "biggest cells to explore". This is because these fields are currently not very useful/reliable.
- (Application: GUI) The following elements of the Node-RED dashboard's "Segmentation" tab will be removed in a future release (probably the next major release): "area chart". This is because the area chart is often buggy and is not very informative.
- (Application: GUI) The following elements of the Node-RED dashboard's "System Monitoring" tab will be removed in a future release (probably the next major release): "GPS status", "navigation", "USB backup". Note that v2024.0.0-alpha.2 already deprecated "USB backup" panel for removal in the next major release. The other deprecations are because most users don't have a working GPS module, and because the navigation panel is not very useful.
- (Application: GUI) The Node-RED dashboard's "WiFi" tab will be removed in a future release (probably the next major release). This is because its left panel is never accurate, and its right panel only partially works, and the actions which can be performed in this tab can take the PlanktoScope into a state which can only be recovered by advanced users or by re-flashing the PlanktoScope's SD card. After removal of this tab, connections to existing Wi-Fi networks should instead be configured by editing `/etc/wpa_supplicant/wpa_supplicant.conf`, or (in the future) by some other command-line interface and/or graphical user interface.

### Fixed

- (Application: backend) The segmenter now correctly sets the `img_rank` metadata field of the EcoTaxa export to `1`, instead of setting it to an incrementing index which makes exports un-importable by EcoTaxa for datasets with more than ~32,000 objects.

## v2024.0.0-beta.3 - 2024-11-30

### Added

- (Application: Documentation) The embedded documentation site now includes [v3 of the protocols.io protocol for PlanktoScope operation](https://www.protocols.io/view/planktoscope-protocol-for-plankton-imaging-bp2l6bq3zgqe/v3)
- (Application: GUI) The landing page now links to v3 of the protocols.io protocol for PlanktoScope operation.
- (Application: GUI) The landing page now shows a warning/info message for users accessing the landing page using any domain name other than `pkscope-{machine-name}.local`, that such a hostname will not work for accessing the PlanktoScope via Wi-Fi router or Ethernet router, and that `pkscope-{machine-name}.local` must be used in such situations.

### Changed

- (Application: hardware controller) The resolution of the camera preview stream has been reduced from 960x720 to 800x600 in an attempt to mitigate hard-to-reproduce preview stream latency problems.
- (Application: hardware controller) The bitrate of the camera preview stream has been reduced slightly from ~8 Mbps to ~7 Mbps.
- (Application: hardware controller) The framerate of the camera preview stream is now explicitly limited to 25 fps.

### Removed

- (Application: Documentation) The embedded documentation site no longer includes [v1 of the protocols.io protocol for PlanktoScope operation](https://www.protocols.io/view/planktoscope-protocol-for-plankton-imaging-bp2l6bq3zgqe/v1)
- (Application: GUI) The landing page no longer links to v1 of the protocols.io protocol for PlanktoScope operation.

### Fixed

- (Breaking change; Application: backend) The segmenter's previously incorrect method for filtering segmented objects by size has now been corrected to filter object sizes by filled area rather than bounding box area, and directly using the mesh size as the threshold for equivalent spherical diameter (ESD) instead of calculating a fictional ESD.
- (System: networking) A regression in handling of the mDNS domain name `pkscope-{machine-name}.local` (likely introduced by v2024.0.0-beta.0) has been fixed, so that now that domain name is resolved again.

## v2024.0.0-beta.2 - 2024-09-19

### Added

- (System: administration) Added a Forklift-deployed script `/usr/libexec/prepare-custom-image` (which must be invoked with `sudo`) to reset machine-specific files and re-enable partition resizing and shut down the Raspberry Pi, in order to automate common tasks needed for making a custom SD card image from a booted Raspberry Pi running the PlanktoScope OS. Support for this script should be considered experimental - this was mainly added as a workaround to a developer-experience regression introduced after v2023.9.0, in which an additional step is now needed after making an SD card image from a previously-booted SD card, or else the image will result in an error message loop ("Partition #2 contains a ext4 signature") during boot and will be unable to resize the image above 8 GB. That step is now included by the added script. Creation of custom SD card images from booted PlanktoScope OS images should still be considered an experimental workflow which may experience breaking changes to the developer experience at any time.

### Changed

- (Application: GUI) Changed the default ISO value from 100 to 150.

### Fixed

- (Application: hardware controller) Changed the hardware controller's libcamera-based camera controller to initialize its default image gain based on camera sensor type in order to match the GUI's default ISO value of 150, instead of initializing default image gain to 1.0 regardless of camera sensor type (which corresponds to an ISO of around 40 or 50).
- (Breaking change; Application: segmenter) Changed the segmenter to include the acquisition ID in the filename of the metadata TSV file included with the EcoTaxa export ZIP archive; this is necessary to allow efficient bulk importing of such ZIP archives into EcoTaxa, which was previously prevented by the use of the same `ecotaxa_export.tsv` filename for all metadata TSV files.
- (Application: GUI) The Grafana server's CPU allowance should now be limited to one core, in an attempt to prevent it from starving other programs of CPU time shortly after booting up under certain situations.

## v2024.0.0-beta.1 - 2024-06-24

### Added

- (Application: GUI) On the `planktoscopehat` SD card image, the Node-RED dashboard's homepage now asks the user to set the hardware version (choosing between v2.3, v2.5, and v2.6) as a first-boot setup step; this dialog replaces the navigation buttons on the homepage until a hardware version is set.
- (Release) A `fairscope-latest` SD card image is now provided which is identical to the `planktoscopehat` SD card image, except that its default settings configuration file is for the v2.6 PlanktoScope hardware (so that the homepage does not ask the user to choose a hardware version).
- (Application: hardware controller) A default `fairscope-latest` hardware config file has been created as the default v2.6 hardware config file.
- (System: administration) The Forklift pallet provided by default as the SD card image is now named (and pinned as) the `factory-reset` staged pallet bundle.
- (System: networking) The `planktoscope.local` mDNS name was deprecated in v2023.9.0-beta.1, but now it's un-deprecated (i.e. official support for this name is added back to the project). As before, you can still use `pkscope.local` or the machine-specific mDNS name (of format `pkscope-{machine-name}.local`) instead of `planktoscope.local`.

### Changed

- (Breaking change; Application: GUI) The default settings configuration file for the `planktoscopehat` SD card image has been reverted to be for the v2.5 PlanktoScope hardware (reverting a change made for v2024.0.0-alpha.2); in v2024.0.0-alpha.2, it was for the v2.6 hardware, while in previous versions it was still for the v2.5 hardware.
- (Breaking change; Application: hardware controller) The default planktoscopehat hardware config file has been rolled back from the default v2.6 hardware config file to the default v2.5 hardware config file. This reverts a change made in v2024.0.0-alpha.1.
- (Release) SD card images are now released with xz compression (as `.img.xz` files) rather than gzip compression (as `.img.gz` files).

### Removed

- (Application: GUI) On the `planktoscopehat` SD card image, a hardware version is no longer set in the default `config.json` file provided on the image. Instead, the user must select their hardware version when they open the Node-RED dashboard's homepage for the first time.
- (Application: GUI) The Node-RED dashboard's Administration page's "Dashboard Errors" panel has been removed, because it doesn't show any useful messages.
- (System) `gcc` has been removed from the SD card image, to help reduce SD card image size.

### Fixed

- (Application: GUI) The flowcell setting from the `config.json` file should now be properly displayed as the default selection on the Node-RED dashboard's "Fluidic Acquisition" page.

## v2024.0.0-beta.0 - 2024-06-07

### Changed

- (Application: GUI) The ISO selector in the "Optic Configuration" page has been changed from a button group to a slider (with an increment of 50), to enable somewhat finer adjustment of the ISO setting.
- (Breaking change; System) The official SD card images of PlanktoScope OS are now based on the 64-bit (arm64) version of the 2024-03-12 build of Raspberry Pi OS 11 (bullseye), instead of the 32-bit (armhf) version of the 2023-05-03 build of Raspberry Pi OS 11 (bullseye). This increases the performance of the Python segmenter, potentially by a factor of 2. This is expected to break compatibility with the raspimjpeg-based imaging module. If you need a 32-bit version of PlanktoScope OS, you will need to run the OS setup scripts following the PlanktoScope project's documentation's "Non-standard installation" guide for software setup.
- (System: administration) The `machine-name` binary is no longer provided by the OS setup scripts, but instead is provided by Forklift for upgradeability (by upgrading the pallet applied to the Raspberry Pi) & removeability/replaceability (by switching to a different pallet which provides a different version of - or does not provide - the `machine-name`).

### Deprecated

- (System) 32-bit versions of PlanktoScope OS (which can be set up on a 32-bit version of Raspberry Pi OS using the OS setup scripts) are no longer officially supported by the project, but they will continue to work for v2024.0.0 of PlanktoScope OS.

### Removed

- (Application: GUI) The landing page's links to Portainer have been removed, as part of the deprecation in v2024.0.0-alpha.2 of the inclusion of Portainer by default in the PlanktoScope OS's SD card images.

### Fixed

- (Application: GUI) The landing page's links to offline PDF copies of the protocols.io protocols for PlanktoScope operation are no longer broken.
- (Application: GUI) The maximum allowed value in the ISO selector in the "Optic Configuration" page has been reduced from 800 to 650, but only for the planktoscopehat version of the Node-RED dashboard; maximum allowed value is still 800 in the adafruithat version of the Node-RED dashboard. This change is because v2024.0.0-alpha.2's change to the scaling factor for converting between ISO settings and camera gains in the picamera2 library has meant that ISO values above 650 were converted to image gain values which were silently rejected for the Raspberry Pi HQ Camera used PlanktoScopes with hardware version at or above v2.3; this, this change prevents users from setting ISO values which would be silently rejected by the Python hardware controller.

## v2024.0.0-alpha.2 - 2024-04-25

### Added

- (System: administration) The hostname can now be customized by modifying the hostname template (with string interpolation for the machine name) in `/etc/hostname-template`.
- (System: administration) The Cockpit configuration can now be customized by adding configuration snippets as drop-in files in `/etc/cockpit/cockpit.conf.d`, and adding origins to allow in `/etc/cockpit/origins.d`, and adding templated origins (with string interpolation for the machine name, the hostname, and the custom domain) to allow in `/etc/cockpit/origins-templates.d`.
- (System: administration) The dnsmasq configuration can now be customized by adding templated drop-in configuration files (with string interpolation for the machine name, the hostname, and the custom domain) in `/etc/dnsmasq-templates.d`, and by modifying the custom domain (which defaults to `pkscope`) in `/etc/custom-domain`.
- (System: administration) The hostapd configuration can now be customized by adding configuration snippets as drop-in files in `/etc/hostapd/hostapd.conf.d`, and adding templated drop-in files (with string interpolation for the machine name, the hostname, and the custom domain) in `/etc/hostapd/hostapd.conf-templates.d`.
- (System: administration) The hosts file can now be customized can now be customized by adding snippets as drop-in files at `/etc/hosts.d`, and and adding templated snippets (with string interpolation for the machine name, the hostname, and the custom domain) in `/etc/hosts-templates.d`.
- (System: administration) SSH host keys for the SSH server are now automatically generated (if deleted or otherwise missing) during every boot, not just during the first boot.

### Changed

- (Breaking change; Application: segmenter) Previously, the segmenter's default behavior was to subtract consecutive masks to try to mitigate image-processing issues with objects which get stuck to the flowcell during imaging. However, when different objects occupied the same space in consecutive frames, the subtraction behavior would subtract one object's mask from the mask of the other object in the following frame, which would produce clearly incorrect masks. This behavior is no longer enabled by default; in order to re-enable it, you should enable the `pipeline-subtract-consecutive-masks` feature flag in the `apps/ps/backend/proc-segmenter` package deployment of the local Forklift pallet and re-apply the pallet (this feature flag sets the segmenter's new `SEGMENTER_PIPELINE_SUBTRACT_CONSECUTIVE_MASKS` environment variable to `true`).
- (Application: hardware controller, GUI) The image quality of frames in the camera preview stream is increased, and frames also have greater width and height.
- (Breaking change; Application: GUI) The default settings configuration file for the `planktoscopehat` SD card image is now for the v2.6 PlanktoScope hardware; previously, it was still for the v2.5 hardware.
- (Breaking change; System: administration) The minimum supported Forklift version for Forklift pallets has increased from v0.4.0 to v0.7.0, due to new integration between Forklift and the filesystem.
- (System: administration) Forklift has been upgraded to v0.7.0, so that pallets are staged before being applied (and with automatic fallback to the last successfully-applied staged pallet), and so that systemd services, `/etc` config files, and some scripts in `/usr` are now managed by Forklift.
- (System: administration) `/etc` is now a overlay filesystem with all manually-edited files saved at `/var/lib/overlays/overrides/etc`.
- (System: administration) `/usr` is now a overlay filesystem with all manually-edited files saved at `/var/lib/overlays/overrides/usr`.

### Deprecated

- (System: administration, troubleshooting; Application: GUI) Portainer will no longer be installed/provided by default after v2024.0.0. This is because it requires inclusion of a relatively large Docker container image in the PlanktoScope OS's SD card image (which is constrained to be up to 2 GB in size so that it can be attached as an upload to GitHub Releases), and because it has an annoying first-time user experience (i.e. that a password must be set within a few minutes of boot, or else the Portainer container must be restarted), and because Dozzle already provides all the basic functionalities needed by most users, and because Portainer has never actually been used for troubleshooting within the past year of the project, and because Portainer has a nontrivial impact on the sizes of the PlanktoScope OS SD card images (which are limited to 2 GB).
- (System: administration; Application: GUI) The "USB backup" functionality of the Node-RED dashboard will be removed in v2024.1.0 (the next release after v2024.0.0). Instead, you should use the datasets file browser for backing up and deleting dataset files on your PlanktoScope.
- (Application: hardware controller) The raspimjpeg-based imaging module in the Python hardware controller has not yet been deleted so that you can change the Python hardware controller code to switch back from the new picamera2-based imaging module if picamera2 ends up causing big problems for you. However, we are deprecating the raspimjpeg-based imaging module, and we will fully delete it in a future release.

### Fixed

- (Application: GUI) The white balance input validation, which previously only allowed gains between 1.0 and 8.0, now allows gains in the full range allowed by the camera (i.e. between 0.0 and 32.0).
- (Application: hardware controller, GUI) The incorrect scaling factor for converting between ISO settings (in the Node-RED dashboard) and image gains in the new picamera2-based imager is fixed.
- (System: networking) Some uncommon edge cases for packet forwarding (e.g. accessing a one of the PlanktoScope's static IP addresses on a network interface not associated with that static IP address) should work now.

## v2024.0.0-alpha.1 - 2024-03-26

### Changed

- (Breaking change; System: setup) The word `pscopehat` has been replaced with `planktoscopehat` everywhere. This means that any distro setup scripts/commands you previously used with `pscopehat` should be changed.
- (Breaking change; Application: hardware controller) The hardware controller now uses `picamera2` instead of `raspimjpeg` for camera control. This may require different ISO and white balance gains to be used. It also no longer limits the framerate of the camera preview, so the preview stream should adapt to the bandwidth available on your network connection and the system resources available to your web browser; this may increase resource usage on your web browser.
- (Breaking change; segmenter) EcoTaxa export archive filenames are now saved as `ecotaxa_{acquisition id}.zip` instead of `ecotaxa_{project id}_{date}_{sample id}.zip`, which was long and redundant and (because many devices have incorrect system times) inappropriate for viewing files in a logically sorted order.

### Deprecated

- (Application: GUI) The current Node-RED dashboard (both the version for the Adafruit HAT and the version for the PlanktoScope HAT) is transitioning to maintenance mode: no new features will be added, and any bugs will be only be fixed if someone volunteers to fix them. The current Node-RED dashboard will be completely replaced by a fully-rewritten Node-RED dashboard, though there is no timeline for completion of that new dashboard. Currently, our plan for deprecating and eventually removing the current Node-RED dashboard is as follows: maintenance mode (no new features, only some bugfixes), then deprecation (no maintenance; not enabled by default, but still installed), then removal (not installed by default, but anyone is free to install it and see if it still works); deprecation will not occur before the rewritten Node-RED dashboard is stable for general-purpose usage. If you have concerns, please share your feedback on GitHub, in an email, or on the PlanktoScope Slack.

### Fixed

- (Breaking change; Application: hardware controller) Images acquired by the hardware controller now have more unique filenames (which include an incrementing index and the date of image capture, rather than just the time of the image capture).
- (Breaking change; Application: hardware controller) The hardware controller no longer crashes when invalid values are given for certain camera settings (e.g. null or non-numeric white balance gains).
- (Breaking change; Application: hardware controller) The pixel calibration values have been switched between the default v2.5 hardware config file and the default v2.6 hardware config file, so that each file has the correct pixel calibration.
- (Breaking change; Application: hardware controller) The default hardware configuration file for the `planktoscopehat` SD card image is now for the v2.6 PlanktoScope hardware; previously, it was (incorrectly) a mixture of v2.5 and v2.6 optical settings.
- (Breaking change; Application: segmenter) The segmenter now runs as `root` (instead of `pi`) in the Docker container for it, so that it doesn't break on various actual & potential edge cases of files/directories being created with `root` ownership (rather than `pi` ownership) before being bind mounted into the container.
- (Application: hardware controller) The camera no longer overexposes captured images compared to the camera preview stream, and it no longer produces camera timeout errors.
- (Application: segmenter) The segmenter should no longer have file permissions errors when trying to read or write files in directories created by Docker or by the Python hardware controller.

## v2024.0.0-alpha.0 - 2024-02-06

### Added

- (System: networking) Added support to share internet access and browser application access over additional network interfaces: a second Wi-Fi module, an additional Ethernet adapter, and a USB networking interface (made by plugging a phone to the Raspberry Pi in USB tethering mode).
- (Application: GUI) The "System Monitoring" page now shows the current system time on the Raspberry Pi and the current time in the web browser of the client device.
- (Application: GUI) The "System Monitoring" page now detects when the Raspberry Pi's system time is very different from the web browser's time, and shows a message and a button to change the Raspberry Pi's system time to match the web browser's time.
- (Application: GUI) The "System Monitoring" page's system metrics panel is now collapsible, and it now includes an expandable "Detailed History" subsection to view additional information.
- (System: administration) Added Dozzle as a viewer for Docker container logs.
- (System: networking) Added `lynx` as an alternative terminal web browser to `w3m` for trying to work through captive portals on the Cockpit terminal.
- (System: administration) Added Prometheus as a metrics collection & storage system.
- (System: administration) Added Grafana as a metrics visualization & alerting system.

### Changed

- (Application: GUI) The "System Monitoring" page now uses a Grafana dashboard to display metrics.
- (Application: GUI) The "Fluidic Acquisition" page now uses a numeric text input instead of a slider for adjusting the "Pumped volume" setting, to make it easier to change the setting to a different exact value.
- (Application: GUI) On the "Sample" page, the input fields of the "Sample Location"/"Net Throw Location"/"Net Retrieval Location"/"Culture Date and Time" panels no longer get cleared when pressing the "Validate" button.
- (System: administration) Docker commands can now be run without `sudo`.
- (System: security) `ufw` has been replaced with `firewalld`. However, `firewalld` has not yet been properly configured.
- (System) The PlanktoScope's machine name is now saved to `/var/lib/planktoscope/machine-name` instead of `/home/pi/.local/etc/machine-name`, and it's now saved without a trailing newline.
- (Application: segmenter) The segmenter is now built and run as a Docker container.

### Removed

- (Application: GUI) The "System Monitoring" page no longer displays a gauge for the CPU usage, since that information does not need to be monitored to ensure system stability & usability. Instead, a CPU usage history graph can be found in the new "Detailed History" subsection.
- (System: administration) Removed `cockpit-storaged`, which was not useful enough to justify the number (and size of) unneeded dependencies it pulled in for the PlanktoScope software SD card image.
- (System: setup) Removed some unnecessary `apt-get update` commands for a very minor speed-up in the distro setup process.

### Fixed

- (Application: GUI) The "Filtered volume" field (on the "Sample" page) is now saved as the `sample_total_volume` metadata field for all sample types, not just horizontal Plankton tows (corresponding to the "Plankton net", "High Speed Net", and "Tara decknet" sample types).
- (System) Boot time has been made faster by approximately 1 minute.
- (Application: GUI) On Mozilla Firefox, the embedded file browser in the Node-RED dashboard's "Gallery" page should now consistently load with the correct height, instead of sometimes loading with an absurdly small height.
- (System: networking) The Raspberry Pi now correctly detects a phone connected in USB tethering mode to share internet access regardless of when the phone was connected, instead of only detecting that phone if USB tethering mode was enabled early in startup (specifically, before the `dhcpcd` service had started).
- (System: networking) Functionality for automatically updating the `/etc/hosts` file and the hostname based on the machine name has now been split into two separate system services, `planktoscope-org.update-hosts-machine-name.service` and `planktoscope-org.update-hostname-machine-name.service`.
- (Application: segmenter) An extraneous `export` directory should no longer be created by the segmenter under `/home/pi/PlanktoScope`. The correct directory is `/home/pi/data/export`.

## v2023.9.0 - 2023-12-30

(this release involves no changes from v2023.9.0-beta.2; it's just a promotion of v2023.9.0-beta.2 to a stable release)

## v2023.9.0-beta.2 - 2023-12-02

### Added

- (Application) A hardware configuration file for PlanktoScope hardware v2.6, which was previously missing, has been added. It is now the default hardware configuration file for `pscopehat` builds of the PlanktoScope distro.

### Changed

- (System: infrastructure) Forklift has been upgraded from v0.3.1 to v0.4.0, which includes breaking changes to the schema of Forklift repositories and pallets.

### Removed

- (Application: documentation) The offline documentation included on the PlanktoScope now omits the hardware setup guides.
- (Application: backend) The segmenter's minimal use of Morphocut has now been fully removed.

### Fixed

- (Application: GUI) The white balance gains are now only validated and sent to the backend _after_ the user changes focus away from the input field, instead of being validated and sent 300 ms after the user pauses while editing the value in the input field. This prevents the input validation from being run while the user is still editing the value.
- (Application) The default brightness of the illumination LED for the pscopehat version of the backend (for the custom PlanktoScope HAT) has been reduced; this a temporary workaround to a bug with raspimjpeg where saved images are overexposed even on the default brightness settings with minimum shutter speed and ISO, despite the brightness of raspimjpeg's camera preview looking reasonable (see https://github.com/fairscope/PlanktoScope/issues/259 for details).
- (Application: GUI) In the "Sample" page, when the minimal & maximal fraction size fields and min & max sampling depth fields are both displayed simultaneously, now the adafruithat version of the Node-RED dashboard shows the fraction size fields on one row and the sampling depth fields on another row, rather than showing them in adjacent columns. This way, the adafruithat version of the Node-RED dashboard now matches the layout in the pscopehat version of the Node-RED dashboard.
- (Application: GUI) The "System Monitoring" page now correctly displays the PlanktoScope hardware version in the "Information" panel's "Instrument Type" field.
- (Application: GUI) The "System Monitoring" and "Fluidic Acquisition" pages now display a software version string which is either a tagged version (e.g. `v2023.9.0-beta.1`) when the version is tagged, or else a pseudoversion (e.g. `v2023.9.0-beta.1-36-gf276e84`) which contains an abbreviated commit SHA and a list of the number of commits since the last tagged version. This version string is now also used for the `acq_software` metadata field.
- (Application: GUI) The `process_commit` metadata field is now set once again. Now it depends on the new installer script provided by the [github.com/PlanktoScope/install.planktoscope.community](https://github.com/PlanktoScope/install.planktoscope.community) repo.
- (Application: GUI) The `process_source` metadata field is no longer hard-coded in the Node-RED dashboard. Now it depends on the new installer script provided by the [github.com/PlanktoScope/install.planktoscope.community](https://github.com/PlanktoScope/install.planktoscope.community) repo.
- (System: infrastructure) The SD card setup scripts now apply the Forklift pallet in order to create the Docker Compose services and resources ahead-of-time (rather than waiting for the first boot to do that work), so that the first boot of the SD card image will be much faster.
- (System: infrastructure) The distro setup scripts now work even if they are run from a repository downloaded to some path other than `/home/pi/PlanktoScope`.
- (Application: GUI) The landing page now links to the new project documentation site for online documentation, instead of the old project documentation site.

## v2023.9.0-beta.1 - 2023-09-14

### Added

- (System: networking) The PlanktoScope can now also be accessed using the domain name `pkscope.local` from any web browser where `planktoscope.local` previously worked. We recommend using http://pkscope.local instead of http://planktoscope.local to access your PlanktoScope, for consistency with other domain name formats (see the "Changes" section for details).
- (System: administration, networking) In operating system's networking configuration files which have lines which are automatically generated based on the PlanktoScope's machine name, those lines now have accompanying code comments which explain the correct files to edit in order to make changes which will persist across device reboots.
- (System: administration, networking) You can now check the machine name at `/home/pi/.local/etc/machine-name`. It's updated when the PlanktoScope boots.
- (System: administration; Application: GUI) The Node-RED dashboard now provides some context on the "Administration" page for how to access the logs linked to from that page, and which links to use for providing logs on GitHub or Slack.
- (System: administration; Application: GUI) The Node-RED dashboard now provides some additional information about the side-effects of selecting a hardware version on the "Hardware Settings" page, specifically that the white balance settings will be overwritten.

### Changed

- (Major user-facing change; System: networking) The top-level domain for domain names of format `home.planktoscope` and `{machine-name}.planktoscope` (e.g. http://metal-slope-23501.planktoscope) has been changed from `planktoscope` to `pkscope`, so that the domain names are now of format `home.pkscope` and `{machine-name}.pkscope`. Similarly, the machine-specific mDNS name has been changed from format `planktoscope-{machine-name}.local` to `pkscope-{machine-name}.local`.
- (User-facing change; System: networking) The SSIDs of wifi hotspots generated by the PlanktoScope has been changed from the format `PlanktoScope {machine-name}` to the format `pkscope-{machine-name}`. This makes it easier to determine the machine-specific mDNS URL: just add `.local`, to get `pkscope-{machine-name}.local` (e.g. `pkscope-metal-slope-23501.local`).
- (User-facing change; Application: backend) The Python backend now uses the new machine naming scheme everywhere.
- (System: networking) The default hostname and SSID (used only in certain unexpected situations when a machine name cannot be determined) have both been shortened from `planktoscope` to `pkscope`.
- (System: networking) The SSID format is now specified in `/home/pi/.local/etc/hostapd/ssid.snippet`, instead of `/home/pi/.local/bin/update-ssid-machine-name.sh`.
- (Application: backend) The backend now also uses the machine name in the new scheme, by loading the name from from a file (currently at `/home/pi/.local/etc/machine-name`) which is automatically generated by the operating system.

### Deprecated

- (System: networking) The `planktoscope.local` mDNS name is no longer recommended. We will continue to support it for the foreseeable future (and definitely for at least one year), but we recommend using `pkscope.local` or the machine-specific mDNS name (of format `pkscope-{machine-name}.local`) instead.
- (Application: backend) The Python backend's logs still print machine names in the old naming scheme, to help instrument operators with the naming scheme transition (so that they can identify how each machine was renamed). The machine names in this old naming scheme will be removed in a future release - probably the next release.
- (Application: backend) The old "Baba"-based machine naming scheme should no longer be used. The `uuidName` module will be removed the next stable release (the stable release after v2023.9.0).

### Removed

- (System: administration, networking) The auto-generated `/home/pi/.local/etc/cockpit/origins` file has been removed, because it does not need to be persisted after being generated. Instead, a temporary file is generated and removed after being used.
- (System: administration, networking) The default `/home/pi/.local/etc/hosts` file has been removed from the setup files. Instead, it is now automatically generated by the setup scripts.

### Fixed

- (System: networking) The PlanktoScope no longer generates any machine names or SSIDs which are so long that they prevent the wifi hotspot network from being brought up.
- (Application: backend) The segmenter no longer crashes and fails to respond immediately after attempting to start segmentation.
- (Application: preset settings, GUI) The default setting for the pscopehat version of the Node-RED dashboard is now the 300 um capillary, since that version of the hardware is meant to be used with 300 um capillaries. Previously, the default was the 200 um ibidi slide.
- (Application: preset settings) All default settings for all hardware versions now include a default pixel size calibration of 0.75 um/pixel. Previously, the default settings for v2.1 and v2.3 were missing this setting, which would cause the segmenter to crash when processing datasets generated on PlanktoScopes using the v2.1 or v2.3 hardware settings.
- (Application: preset settings, GUI) The Node-RED dashboard now correctly lists the selected hardware version in the "Hardware Settings" page's "Hardware Version" dropdown menu upon startup.
- (Application: GUI) The Node-RED dashboard now (hopefully) is able to determine the camera type from the Python backend.

## v2023.9.0-beta.0 - 2023-09-02

### Added

- (System: networking) Traffic is now routed with Network Address Translation between the Ethernet and Wi-Fi network interfaces. This means that if the PlanktoScope has internet access through an Ethernet connection, it will share that internet access to devices connected to its Wi-Fi hotspot; and if the PlanktoScope has internet access through a Wi-Fi connection, it will share that internet access to devices connected to its Ethernet port.
- (System: networking) Now both `192.168.4.1` and `192.168.5.1` can be used to access your PlanktoScope when your computer is connected directly to it, regardless of whether you are connecting over an Ethernet cable or the PlanktoScope's Wi-Fi hotspot.
- (System: networking) Previously the PlanktoScope could be connected to from `192.168.4.1` (over Wi-Fi, when running in wireless AP mode), `192.168.5.1` (over Ethernet), and `planktoscope.local` (over Wi-Fi or Ethernet, from a client device with mDNS support); this meant that Android devices could only connect to the PlanktoScope at `192.168.4.1`, as they lack mDNS support. Now, client devices - even those without mDNS support - can connect to the PlanktoScope at `home.planktoscope`, and/or URLs like `clear-field-33719.planktoscope` and `planktoscope-clear-field-33719.local` (where `clear-field-33719` is replaced with the PlanktoScope's Raspberry Pi's machine name, which is also part of the name of the PlanktoScope's Wi-Fi network - e.g. "PlanktoScope clear-field-33719").
- (Application: Documentation) An offline copy of the PlanktoScope project documentation is now provided at URL path `/ps/docs/` (so e.g. it's accessible at http://home.planktoscope/ps/docs/)
- (Application: GUI) The Node-RED dashboard's "Hardware Settings" page now includes a drop-down menu item to select "PlanktoScope v2.5" as an allowed hardware version.
- (Application: GUI, administration) The Node-RED dashboard now generates a notification whenever it restarts the Python backend. This provides visibility for the user when changing the hardware version triggers a restart of the Python backend.
- (System: administration, troubleshooting, GUI) A [Cockpit](https://cockpit-project.org/) system administration dashboard is now installed and made accessible at URL path `/admin/cockpit/` (so e.g. it's accessible at http://home.planktoscope/admin/cockpit/).
- (System: administration, troubleshooting, GUI) A [filebrowser](https://github.com/filebrowser/filebrowser) instance, allowing you to manage and edit files anywhere in the Raspberry Pi's SD card, is now installed and made accessible at URL path `/admin/fs/` (so e.g. it's accessible at http://home.planktoscope/admin/fs/)
- (System: administration, troubleshooting, GUI) A [Portainer](https://www.portainer.io/) administration dashboard for Docker is now installed and made accessible at URL path `/admin/portainer/` (so e.g. it's accessible at http://home.planktoscope/admin/portainer/). Note that you will need to open Portainer within a few minutes after booting (or rebooting) your PlanktoScope in order to create an admin account for Portainer.
- (System: administration) [Docker](https://www.docker.com/) is now installed. We are using it to deliver various applications in a way that will eventually enable safe and easy upgrades.
- (System: administration, troubleshooting) [w3m](https://en.wikipedia.org/wiki/W3m) is now installed, enabling terminal-based interaction with some Wi-Fi network captive portals to obtain internet access on the PlanktoScope. For captive portals which require Javascript, we recommend instead using [browsh](https://www.brow.sh/) as a Docker container; we don't provide browsh in the default SD card image because it adds ~250 MB of dependencies to the image.

### Changed

- (User-facing change; System: administration) The file browser on port 80 for viewing datasets has now been moved to path `/ps/data/browse/` (so e.g. it's accessible at http://home.planktoscope/ps/data/browse/ ), and it is now implemented using [filebrowser](https://github.com/filebrowser/filebrowser), so that now you can delete folders, download folders, preview images, etc. As before, you can still access this from the "Gallery" page of the Node-RED dashboard.
- (User-facing change; Application: GUI) If you navigate the PlanktoScope in your web browser on port 80 (or without specifying a port) (e.g. with URLs like `http://home.planktoscope` or `http://planktoscope.local`), your browser will show a landing page with a list of links for easy access to the Node-RED dashboard, documentation, other embedded applications, and reference information about your PlanktoScope.
- (User-facing change; Application: GUI) Previously, the Node-RED dashboard was accessed on the path `/ui` on port 1880, e.g. with URLs like `http://planktoscope.local:1880/ui` or `http://192.168.4.1:1880/ui`; now, it should be accessed via a link on the landing page.
- (User-facing change; System: networking) Previously, PlanktoScope machine names were generated as gibberish words like "Babaxio-Detuiau", and the machine names were used as the names of the private Wi-Fi networks generated by the PlanktoScope in wireless AP mode. However, the machine names created by this naming scheme were often difficult to pronounce, remember, and type for people in various languages, and the naming scheme sometimes generated names which sounded like curses or insults in some languages. Now, PlanktoScope machine names are generated as a combination of two words and a number up to five digits long; words are selected from pre-built lists in a language which can be chosen based on localization settings. Currently, word lists are only provided in US English, resulting in names like "metal-slope-23501", "conscious-pocket-1684", and "plant-range-10581"; however, word lists can be added for other languages in the future, and a user interface will eventually be provided for changing localization settings.
- (User-facing change; Application: GUI) Selecting a hardware version on the "Hardware Settings" page of the Node-RED dashboard now causes a default hardware preset for that version to overwrite the entire `hardware.json` file, and the Node-RED dashboard will reload the settings; this prevents the `hardware.json` file from being changed into an inconsistent mixture of settings for different hardware versions, which was the previous (incorrect) behavior. The description on the "Hardware Settings" page is also now more specific about what happens when a hardware version is selected.
- (User-facing change; Application: GUI, troubleshooting) Previously, the Node-RED dashboard's "Administration" page merged log entries from every component of the Python backend and the Node-RED dashboard. Now, the Node-RED dashboard instead displays links to separate Cockpit log-viewing pages (which by default are accessed with username `pi` and password `copepode`) for the Node-RED dashboard, the backend's hardware controller, and the backend's segmenter, and links to filebrowser directories for all log files created by the backend's hardware controller and segmenter.
- (User-facing change; System: GUI) Previously, the Node-RED flow editor was accessed directly on port 1880, e.g. with URLs like `http://planktoscope.local:1880` or `http://192.168.4.1:1880`; now, it should be accessed via a link on the landing page .
- (System: networking) Previously, PlanktoScopes all had `planktoscope` as their hostname. Now, the hostname is of the format `planktoscope-<machine-name>`, e.g. `planktoscope-metal-slope-23501` or `planktoscope-plant-range-10581`.
- (Likely user-facing change; System: networking) The default Wi-Fi country has been changed from `FR` (France) to `US` (USA).
- (Likely user-facing change; System: networking) Previously the autohotspot script considered receiving an IP address assignment from the connected Wi-Fi network as the criterion for determining whether the Wi-Fi connection was successful. Now the autohotspot script tries to ping `google.com` to determine whether the connection was successful, so that the autohotspot script will revert to wireless AP mode if no internet access is available over the Wi-Fi network (e.g. if the connected Wi-Fi network is actually behaving like a captive portal, which would prevent the PlanktoScope from being accessed via a VPN over the internet - in which case the PlanktoScope would become accessible only over an Ethernet cable). This change is meant to make it easier to fix a PlanktoScope's Wi-Fi connection configuration when that configuration makes internet access impossible.
- (System: networking, troubleshooting) Previously the autohotspot script would print the MAC addresses and SSIDs of all Wi-Fi networks found by scanning. Now it only prints the SSIDs of Wi-Fi networks found by scanning and avoids printing duplicate SSIDs, for more concise service logs.
- (System: networking, troubleshooting) When the autohotspot script fails to connect to google.com, it will also print some diagnostic information by attempting to ping `1.1.1.1` (the static IP address of Cloudflare DNS, so a ping without DNS lookup) and checking whether the Wi-Fi network assigned an IP address to the Raspberry Pi, and reporting the results. This enables better troubleshooting of internet access issues on Wi-Fi networks.
- (System: networking) Previously the autohotspot script was run every 5 minutes to scan for available Wi-Fi networks. Now it is run every 2 minutes, so that the PlanktoScope will connect more quickly to a Wi-Fi network which has just appeared.
- (System: networking) Previously the autohotspot script and the dhcpcd service would both try to manage when to start and stop the dnsmasq service. Now, the dnsmasq service always runs. This change was made to simplify the network configuration so that it would be easier to understand, troubleshoot, and maintain.
- (System: networking) Previously the autohotspot script would use a mixture of dhcpcd and wpa_supplicant as entrypoints for Wi-Fi network connection management. Now, dhcpcd is used to manage wpa_supplicant, and the autohotspot script only interacts with dhcpcd. This change was made to simplify the network configuration so that it would be easier to understand, troubleshoot, and maintain. Note that, in the future, wpa_supplicant and dhcpcd may be replaced with [NetworkManager](https://networkmanager.dev/).
- (System: networking) The autohotspot script has undergone a major refactoring, which may accidentally introduce bugs.
- (Application: Backend, GUI) The Node-RED dashboard no longer supervises the Python backend; instead, it delegates that work to systemd.
- (Application: Backend) Log files from the Python backend are no longer saved to `/home/pi`, but instead to subdirectories for the backend components under `/home/pi/device-backend-logs`. Note: the locations of log files may be changed again in the future, and/or file logging may be changed to use a different systemd-based mechanism in the future.
- (System) The `/usr/bin/stepper-disable` and `/usr/bin/autohotspotN` scripts have been moved to `/home/pi/.local/bin/release-gpio-steppers.sh` and `/home/pi/.local/bin/autohotspot.sh`, respectively.
- (System) The `gpio-init.service` systemd service has been renamed to `planktoscope-org.init-gpio-steppers.service`.
- (System) Previously the `en_DK.UTF-8` locale was used for everything. Now it is only used for time, measurements, and paper dimensions, and the `en_US.UTF-8` locale is the base locale for everything else. In the future we may provide GUI functionality for changing the base locale.
- (System) The chrony configuration has been simplified, but it may be broken.
- (System) The default timezone is now officially set to UTC, and we will be using UTC as the standard system time zone for all PlanktoScopes. Previously, the pre-built SD card images provided by this project used UTC as the timezone, but the "Expert Setup" instructions for manually setting up the PlanktoScope software did not specify a time zone to use.
- (System, Dependencies) The base OS is now the 2023-05-03 release of Raspberry Pi OS Bullseye.
- (Application: Backend) The Python backend has now been split into a hardware controller (of which there are two versions for the Adafruit HAT and the custom PlanktoScope HAT, respectively) and a data processing segmenter. These two components are run separately, so that a crash in one component will not automatically cause a crash in the other component. Additionally, their dependencies are managed separately.
- (Application: Backend, Dependencies) The Python backend and Node-RED dashboard's indirect dependencies are now version-locked to improve the reproducibility of the OS setup script independently of when the script is run.

### Deprecated

- (Application: GUI) In a future release (potentially as early as v2023.12.0), the Node-RED editor and Node-RED dashboard will not be accessible at all over port 1880. In this release, you can still access the Node-RED dashboard at path `/ps/node-red-v2/ui` on port 1880, but the embedded image streams and file gallery will not be properly displayed; and you can access the Node-RED editor at path `/admin/ps/node-red-v2` on port 1880. However, you should instead access the Node-RED editor and Node-RED dashboard via the links on the PlanktoScope's landing page.
- (Application: GUI) In a future release (timeline not yet decided), the version of the Node-RED dashboard for the Adafruit HAT will stop receiving new features even as the version of the Node-RED dashboard for the custom PlanktoScope HAT continues receiving new features. However, we will continue to fix bugs in the Node-RED dashboard for the Adafruit HAT, and we will continue to build SD card images for the Adafruit HAT which will also include new features in other software components.

### Removed

- (User-facing removal; Application: GUI) The Node-RED dashboard no longer allows selection of "PlanktoScope v1.0" or "PlanktoScope v2.2 (waveshare HAT)" as the hardware version. Those hardware versions are no longer supported by the software.
- (User-facing removal; System: networking) Now `planktoscope.local` only works for devices connected directly to the PlanktoScope, either via an Ethernet cable or over Wi-Fi when the PlanktoScope is running in wireless AP mode. `planktoscope.local` no longer works on other networks, such as LANs or mesh VPNs, which the PlanktoScope might be connected to. On such networks, the machine-specific mDNS name (of format `planktoscope-<machine-name>.local`) should be used instead.
- (System: administration) The Git-based software update system (exposed in the Node-RED dashboard's "Adminisration" page) has been removed, since it was reported to behave problematically anyways. In the future, we will use a system based on Docker for safer and easier software updates.

### Fixed

- (Major fault-tolerance improvement; Application: GUI) When an invalid value is entered for the red or blue white balance gain on the Node-RED dashboard's "Optic Configuration" page, that value is now ignored, a notification is displayed about the invalid value, and the white balance gain is reset to the last valid value (loaded from the `hardware.json` configuration file). This fixes [issue #166](https://github.com/fairscope/PlanktoScope/issues/166) by preventing the Node-RED dashboard from saving an invalid value to the `hardware.json` file, which would crash the Python hardware controller after the next boot (or after the next time the Python hardware controller was restarted).
- (Major quality-of-life improvement; Backend: dependencies) The `adafruit-blinka` and `adafruit-platformdetect` dependencies are now updated to their latest version, so that Python hardware controller will work on PlanktoScopes with recent (i.e. post-2021) versions of the Adafruit HAT.
- (Application: GUI, troubleshooting) Previously, the Node-RED dashboard would often fail to display the log output from the Python backend. Now, it should always make the logs accessible (either by the links to Cockpit log viewer or by the links to the log file browser).
- (System: networking) Previously the autohotspot script would not ignore any networks which were commented out in the `/etc/wpa_supplicant/wpa_supplicant.conf` file when checking if any networks found by scanning matched networks were specified in the `wpa_supplicant.conf` file; now it ignores them, so that commented-out networks don't incorrectly prevent the autohotspot from going into wireless AP mode.
- (System: networking) Previously the autohotspot script would always wait 20 seconds after attempting to connect to a Wi-Fi network before checking whether the connection was successful, even if it didn't actually need to wait 20 seconds. Now the autohotspot script repeatedly attempts to ping google.com with a timeout of 2 seconds per attempt and a maximum of 10 attempts, so that the autohotspot script only waits as long as a necessary to determine that a Wi-Fi network connection has succeeded.
- (System: networking) Previously the autohotspot script could decide that the SSID scan results were available even if no SSIDs were found (despite local Wi-Fi networks being active). Now an empty SSID scan result is treated as a condition where a re-scan is required.
- (System: networking) Previously the log messages from the autohotspot script had inconsistent capitalization and grammar, and slightly unclear wording. Those have now been made more clear and consistent.
- (Application: backend) The default `hardware.json` file for PlanktoScope v2.1 had incorrect keys for the white balance values; the keys have now been fixed.

## v2.3.0 - 2021-12-20

### Added

- A basic working image segmenter.
- Direct connections over Ethernet.
- A "Lab culture" sample type, where location is set to the South Pole, and sample collection time and date are set by default to the current time and date on the Raspberry Pi but can be changed. ([#74](https://github.com/fairscope/PlanktoScope/issues/74))
- A "Test" sample type, where location is set to the South Pole, and sample collection time and date are always set to the current time and date on the Raspberry Pi.
- A selector in the Node-RED dashboard for the machine hardware version ([#98](https://github.com/fairscope/PlanktoScope/issues/98))

### Changed

- Various parts of the UI (we do not have a list of specific changes).
- Node-RED is now upgraded to v2.0 ([#97](https://github.com/fairscope/PlanktoScope/issues/97))
- The base OS is now the 2021-12-03 release of Raspberry Pi OS Buster.

### Fixed

- Various issues with accessing the Node-RED dashboard via http://planktoscope.local:1880/ui .
- Various issues with Node-RED ([#80](https://github.com/fairscope/PlanktoScope/issues/80), [#91](https://github.com/fairscope/PlanktoScope/issues/91), [#87](https://github.com/fairscope/PlanktoScope/issues/87), [#96](https://github.com/fairscope/PlanktoScope/issues/96))

## v2.2.1 - 2021-05-10

### Added

- The ability for developers to change the PlanktoScope repository to a development branch from the Node-RED dashboard.

### Fixed

- Various bugs (we do not have a list of specific changes)

## v2.2.0 - 2021-02-23

### Added

- Support for Raspberry Pi HQ cameras.
- Control of image white balance.
- A Node-RED dashboard panel to copy all data from `/home/pi/data` to a USB drive.
- Integrity check of the generated files (for now only for raw pictures and `metadata.json` files). A file called `integrity.check` is created alongside the images. This file contains one line per file, with the filename, its size and a checksum of both its filename and its content.
- A file gallery to browse data files in the `/home/pi/data` directory.
- A way to update the PlanktoScope software repository on the Raspberry Pi.
- A Node-RED dashboard panel to choose a wifi network to connect to.
- A Node-RED tab to enter the configuration of the hardware.

### Changed

- (Breaking change) The UI has been changed (we do not have a list of specific changes)

### Fixed

- Random camera crash solved: instead of using the python picamera library, we now use a compiled binary, `raspimjpeg`, controlled through a FIFO pipe

## v2.1.0 - 2020-10-14

### Added

- If the Raspberry Pi is configured (via the `/etc/wpa_supplicant/wpa_supplicant.conf` file) to connect to an existing wifi network, it will try to connect to the network; and it will only start its own wifi hotspot if it failed to connect.
- If the Raspberry Pi is connected to the internet via its Ethernet port, it will share internet access to devices connected to the Raspberry Pi's wifi hotspot.
- (Documentation) Information has been added about ribbon cable assembly.
- (Documentation) Information has been added about how to back up the SD card.

### Changed

- (Breaking change) The OS is now based on Raspberry OS Lite, so there is no graphical desktop.
- (Breaking change) The wifi network is now named `PlanktoScope`, and the password to it is now `copepode`.
- (Breaking change) The default user is now `pi`, and the default password is `copepode` for this user.
- (Breaking change) All raw and processed data files are now stored in the directory `/home/pi/data`.
- The software has undergone a major refactoring, which may accidentally introduce some bugs.
