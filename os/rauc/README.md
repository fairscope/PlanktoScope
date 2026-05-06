# RAUC

[RAUC](https://rauc.readthedocs.io/en/latest/) is the software we use to handle software updates on the PlanktoScope.

We have an A/B partitioning setup see [os/image](../image) for which RAUC is aware of.

## Create an bundle

A bundle is an update that will be installed on a slot.

```sh
cd os/rauc
sudo ./rauc.js create-bundle /dev/device B
```

This will create a bundle from partitions `FIRMWARE_B` and `ROOT_B` on device `/dev/device`.

## Install a bundle

```sh
rauc install PlanktoScope-update-xxx-xx-xx.raucb
```

This will install the update on the slot that is not the booted one. See `rauc status`.
