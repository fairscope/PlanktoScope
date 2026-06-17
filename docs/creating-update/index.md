# Creating a new update

Since PlanktoScope OS v2026, we use [RAUC](https://rauc.readthedocs.io/) to create and install software updates.

The PlanktoScope contains 2 slots; A and B; each able to host the entirety of the operating system.

To create an update

```sh
cd /opt/PlanktoScope/os/pkos
# Boot to slot A
sudo ./pkos reboot A
# Install RPI OS to slot B
rauc install PlanktoScopeOS-2026-04-21-raspios.raucb
# Boot to slot B
sudo ./pkos reboot B
# Run setup scripts
sudo ./pkos prepare
# Boot to slot A
sudo ./pkos reboot A
# Create bundle
# TODO
```

You can also swap A and B.
