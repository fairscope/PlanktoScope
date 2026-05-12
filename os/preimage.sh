#!/bin/bash -eux

# https://systemd.io/BUILDING_IMAGES/
sudo rm -f /var/lib/systemd/random-seed
sudo rm -f /var/lib/systemd/credential.secret

sudo rm -f /etc/ssh/ssh_host_*_key*

uv clean --force
npm cache clean --force

rm -rf /opt/PlanktoScope/documentation
sudo rm -rf /srv/docs


# Clear machine-id so that it will be regenerated on the next boot
# This is also the condition for ConditionFirstBoot=yes
sudo rm /data/machine-id
