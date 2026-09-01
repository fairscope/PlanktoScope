# pkos

`pkos` is a helper CLI program to perform PlanktoScope OS specific commands.

## Creating a bundle

You can swap A and B

1. Boot to slot A
2. Run [`prepare`](#prepare)
3. Boot to slot B
4. Run [`create-bundle`](#create-bundle)

This will create a bundle of partitions `FIRMWARE_A` and `ROOT_A` from device `/dev/$device`.

A bundle can be installed to either slot. So please consider:

* Files on `FIRMWARE_A` and `FIRMWARE_B` should be considered identical.
* Files on `ROOT_A` and `ROOT_B` should be considered identical.
* A bundle must work for any slot

We use the Raspberry Pi firmware and bootloader to dynamically switch between A and B.

## Commands

### slot

Returns the current slot bootname (A or B)

```sh
sudo ./pkos.js slot
A
```

### reboot

Reboot to a specific slot using its bootname (A or B)

```sh
sudo ./pkos.js reboot B
```

### install-rpios

Install Raspberry Pi OS from a RPI OS img to a slot

```sh
sudo NODE_DEBUG=execa ./pkos.js install-rpios /dev/device A
```

### prepare

Run the preparation scripts on the current slot. This steps is needed before creating a bundle from the slot.

```sh
sudo ./pkos.js prepare
```

### create-bundle

Create a rauc bundle (`.raucb`). `$version` is used in the filename only.

```sh
sudo NODE_DEBUG=execa ./pkos.js create-bundle /dev/$device A $version
```
