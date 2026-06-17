# Creating a new update

Since PlanktoScope OS v2026, we use [RAUC](https://rauc.readthedocs.io/) to create and install software updates.

The PlanktoScope contains 2 slots; A and B; each able to host the entirety of the operating system.

To create an update

```sh
# Boot to slot A
cd /opt/PlanktoScope/os/pkos
sudo ./pkos.js reboot A
# Install RPI OS to slot B
rauc install PlanktoScopeOS-2026-04-21-raspios.raucb
# Boot to slot B
cd /opt/PlanktoScope/os/pkos
sudo ./pkos.js reboot B
# Install deps
sudo apt install git just
git clone git@github.com:fairscope/PlanktoScope.git
sudo mv PlanktoScope /opt/PlanktoScope
sudo chown -R pi:pi /opt/PlanktoScope
# Run setup scripts
cd /opt/PlanktoScope/os/pkos
just
./pkos.js prepare
# Boot to slot A
sudo ./pkos.js reboot A
# Create bundle
# TODO
```

You can also swap A and B.
