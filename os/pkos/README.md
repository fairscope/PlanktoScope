# pkos

`pkos` is a helper CLI program to perform PlanktoScope OS specific commands.

## slot

Returns the current slot bootname (A or B)

```sh
sudo ./pkos.js slot
A
```

## reboot

Reboot to a specific slot using its bootname (A or B)

```sh
sudo ./pkos.js reboot B
```

## install-rpios

Install Raspberry Pi OS from a RPI OS img to a slot

```sh
sudo NODE_DEBUG=execa ./pkos.js install-rpios /dev/device A
```

## prepare

Run the preparation scripts on the current slot. This steps is needed before creating a bundle from the slot.

```sh
./pkos.js prepare
```

## create-bundle

A bundle is an update that can be installed on a slot.

```sh
sudo NODE_DEBUG=execa ./pkos.js create-bundle /dev/device B [version]
```

This will create a bundle from partitions `FIRMWARE_B` and `ROOT_B` on device `/dev/device`.
