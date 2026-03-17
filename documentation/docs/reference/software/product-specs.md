# Product Specifications

The PlanktoScope OS includes all software which needs to run on the PlanktoScope's hardware to provide the [overall functionality of a PlanktoScope](../index.md). Product specifications for the PlanktoScope OS are listed below for ranges of software version numbers. To see software versions listed individually in chronological order, refer to the [project release notes](https://github.com/fairscope/PlanktoScope/releases) or the [software changelog](./changelog.md). To understand how to interpret software version numbers, refer to our description of the PlanktoScope OS's [version numbering system](./release-process.md#version-numbering).

## v2025.0.0

Specs for v2025.0.0 are the same as in v2024.0.0, except for the following sections:

- Base operating system: the distro has changed from Raspberry Pi OS 11 (bullseye) to Raspberry Pi OS 12 (bookworm).
- Supported optional addons: additional support for up to one USB Wi-Fi adapter (with a compatible Wi-Fi chipset).
- Forwards-incompatible: now able to run on the Raspberry Pi 5 computer.

### Functionalities

Regular operation:

- Image acquisition: stop-flow imaging (JPEG image output)
- On-board image processing: detection and segmentation of objects (batch-processing only)
- User interfacing: graphical interface accessible through web browser of a connected phone, tablet, or computer
- Export of data for uploading to EcoTaxa

Advanced operations:

- User interfacing: web browser interfaces for system administration, system monitoring, and troubleshooting
- Automation: MQTT-based API
- Application deployment: ability to add software as OCI containers using Docker, optionally via [Forklift](https://docs-edge.planktoscope.community/reference/software/architecture/os/#package-management-with-forklift)
- System configuration: ability to reversibly add, remove, replace, or override OS configuration files via Forklift

### Base operating system

- Distro: Raspberry Pi OS 12 (bookworm)
- Binary target architecture: 64-bit (aarch64, also known as arm64)

### Supported hardware

Minimum for image acquisition (but not sufficient for on-board image processing):

- PlanktoScope: hardware v2.1 with Raspberry Pi 4 Model B computer
- Memory: 1 GB RAM
- Storage: 16 GB capacity

Minimum for full functionality, including on-board image processing:

- Memory: 4 GB RAM
- Storage: 16 GB capacity

Recommended:

- PlanktoScope: hardware v2.5 or v2.6 with Raspberry Pi 4 Model B computer
- Storage: 32 GB capacity

Forwards-incompatibilities:

- Incompatible with the upcoming PlanktoScope hardware v3.

Backwards-incompatibilities:

- Might still work on a Raspberry Pi 3 Model B+ computer or a Raspberry Pi 4 Model B computer with 1 GB of RAM, but compatibility is not tested.

### Supported optional addons

Networking peripherals:

- Up to one phone (Android only) connected by USB cable in USB tethering mode: for internet access.
- Up to one USB-to-Ethernet adapter: either for internet access or for direct access from a connected device.
- Up to one USB Wi-Fi adapter (with [a compatible Wi-Fi chipset](https://github.com/morrownr/USB-WiFi/blob/main/home/USB_WiFi_Adapters_that_are_supported_with_Linux_in-kernel_drivers.md) such as RT5370): either for internet access or for creating an additional Wi-Fi hotspot to enable direct access.

Miscellaneous data sources:

- Up to one Adafruit Ultimate GPS HAT: for system clock synchronization, and for automatic detection of GPS location coordinates.

### System performance

With minimum supported hardware for full functionality:

- On-board image processing: a dataset of 400 raw images is processed in approximately 1 hour

## v2024.0.0

Specs for v2024.0.0 are the same as in v2023.9.0, except for the following sections:

- Base operating system: the binary target architecture has changed from 32-bit to 64-bit.
- Supported optional addons: support for up to one USB-to-Ethernet adapter as an optional addon.
- System performance: on-board image processing speeds have improved (processing speeds have nearly doubled).

### Functionalities

Regular operation:

- Image acquisition: stop-flow imaging (JPEG image output)
- On-board image processing: detection and segmentation of objects (batch-processing only)
- User interfacing: graphical interface accessible through web browser of a connected phone, tablet, or computer
- Export of data for uploading to EcoTaxa

Advanced operations:

- User interfacing: web browser interfaces for system administration, system monitoring, and troubleshooting
- Automation: MQTT-based API
- Application deployment: ability to add software as OCI containers using Docker, optionally via [Forklift](https://docs-edge.planktoscope.community/reference/software/architecture/os/#package-management-with-forklift)
- System configuration: ability to reversibly add, remove, replace, or override OS configuration files via Forklift

### Base operating system

- Distro: Raspberry Pi OS 11 (bullseye)
- Binary target architecture: 64-bit (aarch64, also known as arm64)

### Supported hardware

Minimum for image acquisition (but not sufficient for on-board image processing):

- PlanktoScope: hardware v2.1 with Raspberry Pi 4 Model B computer
- Memory: 1 GB RAM
- Storage: 16 GB capacity

Minimum for full functionality, including on-board image processing:

- Memory: 4 GB RAM
- Storage: 16 GB capacity

Recommended:

- PlanktoScope: hardware v2.5 or v2.6 with Raspberry Pi 4 Model B computer
- Storage: 32 GB capacity

Forwards-incompatibilities:

- Unable to run on the Raspberry Pi 5 computer.
- Incompatible with the upcoming PlanktoScope hardware v3.

Backwards-incompatibilities:

- Might still work on a Raspberry Pi 3 Model B+ computer or a Raspberry Pi 4 Model B computer with 1 GB of RAM, but compatibility is not tested.

### Supported optional addons

Networking peripherals:

- Up to one phone (Android only) connected by USB cable in USB tethering mode: for internet access.
- Up to one USB-to-Ethernet adapter: either for internet access or for direct access from a connected device.

Miscellaneous data sources:

- Up to one Adafruit Ultimate GPS HAT: for system clock synchronization, and for automatic detection of GPS location coordinates.

### System performance

With minimum supported hardware for full functionality:

- On-board image processing: a dataset of 400 raw images is processed in approximately 1 hour

## v2023.9.0

### Functionalities

Regular operation:

- Image acquisition: stop-flow imaging (JPEG image output)
- On-board image processing: detection and segmentation of objects (batch-processing only)
- User interfacing: graphical interface accessible through web browser of a connected phone, tablet, or computer
- Export of data for uploading to EcoTaxa

Advanced operations:

- User interfacing: web browser interfaces for system administration, system monitoring, and troubleshooting
- Automation: MQTT-based API
- Application deployment: ability to add software as OCI containers using Docker, optionally via [Forklift](https://docs-edge.planktoscope.community/reference/software/architecture/os/#package-management-with-forklift)

### Base operating system

- Distro: Raspberry Pi OS 11 (bullseye)
- Binary target architecture: 32-bit only (armhf, also known as armv7)

### Supported hardware

Minimum for image acquisition (but not sufficient for on-board image processing):

- PlanktoScope: hardware v2.1 with Raspberry Pi 4 Model B computer
- Memory: 1 GB RAM
- Storage: 8 GB capacity

Minimum for full functionality, including on-board image processing:

- Memory: 4 GB RAM
- Storage: 16 GB capacity

Recommended:

- PlanktoScope: hardware v2.5 or v2.6 with Raspberry Pi 4 Model B computer
- Storage: 32 GB capacity

Forwards-incompatibilities:

- Unable to run on the Raspberry Pi 5 computer.
- Incompatible with the upcoming PlanktoScope hardware v3.

Backwards-incompatibilities:

- Might still work on a Raspberry Pi 3 Model B+ computer or a Raspberry Pi 4 Model B computer with 1 GB of RAM, but compatibility is not tested.

### Supported optional addons

Networking peripherals:

- Up to one phone (Android only) connected by USB cable in USB tethering mode: for internet access.

Miscellaneous data sources:

- Up to one Adafruit Ultimate GPS HAT: for system clock synchronization, and for automatic detection of GPS location coordinates.

### System performance

With minimum supported hardware for full functionality:

- On-board image processing: a dataset of 400 raw images is processed in approximately 1.5 to 2 hours

## v2.3

### Functionalities

Regular operation:

- Image acquisition: stop-flow imaging (JPEG image output)
- On-board image processing: detection and segmentation of objects (batch-processing only)
- User interfacing: graphical interface accessible through web browser of a connected phone, tablet, or computer
- Export of data for uploading to EcoTaxa

Advanced operations:

- Automation: MQTT-based API

### Base operating system

- Distro: Raspberry Pi OS 11 (bullseye)
- Binary target architecture: 32-bit only (armhf, also known as armv7)

### Supported hardware

Minimum for image acquisition (but not sufficient for on-board image processing):

- PlanktoScope: hardware v2.1 with Raspberry Pi 3 Model B+ computer
- Memory: 1 GB RAM
- Storage: 8 GB capacity

Minimum for full functionality, including on-board image processing:

- PlanktoScope: hardware v2.1 with Raspberry Pi 4 Model B computer
- Memory: 4 GB RAM
- Storage: 16 GB capacity

Recommended for full functionality:

- PlanktoScope: hardware v2.5 or v2.6
- Storage: 32 GB capacity

Forwards-incompatibilities:

- Unable to run on the Raspberry Pi 5 computer.
- Incompatible with the upcoming PlanktoScope hardware v3.
- Incompatible with Adafruit Stepper Motor HATs (used in PlanktoScope hardware v2.1) manufactured after mid-2022.

### Supported optional addons

Networking peripherals:

- Up to one phone (Android only) connected by USB cable in USB tethering mode: for internet access.

Miscellaneous data sources:

- Up to one Adafruit Ultimate GPS HAT: for system clock synchronization, and for automatic detection of GPS location coordinates.

### System performance

With minimum supported hardware for full functionality:

- On-board image processing: a dataset of 400 raw images is processed in approximately 1.5 to 2 hours
