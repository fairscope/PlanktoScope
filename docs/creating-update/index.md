# Creating a new update

Since PlanktoScope OS v2026, we use [RAUC](https://rauc.readthedocs.io/) to create and install software updates.

The PlanktoScope contains 2 slots; A and B; each able to host the entirety of the operating system.

To create an update

```sh
# SSH
ssh pi@xxx

# Install pkos
just -f /opt/PlanktoScope/os/pkos/justfile

# Install RPI OS rauc bundle (see Updating Raspberry Pi OS to create a rauc bundle)
rauc install PlanktoScopeOS-raspios-yyyy-mm-dd.raucb

# Boot to new active slot with Raspberry Pi OS
sudo reboot

# SSH
ssh pixxx

# Make sure it booted to the new install

# Install PlanktoScope software
# This will download and install from `main` branch
# If you want something else clone to `/opt/PlanktoScope` and run `/opt/PlanktoScope/os/setup.sh`
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/FairScope/PlanktoScope/HEAD/os/setup.sh)"

# Reboot
sudo reboot

# Perform basic tests
# Go to http://planktoscope-sponge-bob/ps/node-red-v2/dashboard/preview

# SSH
ssh pixxx

# Run setup scripts
sudo NODE_DEBUG=execa pkos prepare

# Boot to inactive slot
sudo pkos reboot X

# SSH
ssh pi@xxx

# Create bundle
sudo NODE_DEBUG=execa pkos create-bundle /dev/nvme0n1 B 2026.4.0
# It will display the path of the raucb file

# From your computer; download the file
scp pi@xxx:/data/tmp/PlanktoScopeOS-2026.4.0.raucb .
```

You can swap A and B.
