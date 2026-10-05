# Infra

We have a custom runner on GitHub. The base OS is [`2025-10-01-raspios-trixie-arm64-lite.img.xz`](https://downloads.raspberrypi.com/raspios_lite_arm64/images/raspios_lite_arm64-2025-10-02/2025-10-01-raspios-trixie-arm64-lite.img.xz) running on a Raspberry Pi 5.

<details>
    <summary>SHA256 hash</summary>
    62d025b9bc7ca0e1facfec74ae56ac13978b6745c58177f081d39fbb8041ed45
</details>

## Setup

Write the sdcard, choose US internal keyboard layout, `pi` username and `copepode` password. Then:

```sh
sudo apt install -y git
cd ~
git clone https://github.com/fairscope/PlanktoScope.git --depth=1
cd PlanktoScope/infra
./setup.sh

cd ~/actions-runner

# Go to https://github.com/fairscope/PlanktoScope/settings/actions/runners/new?arch=arm64&os=linux

# Enter the  "config.sh" instruction only
# TODO: Use the API https://docs.github.com/en/rest/actions/self-hosted-runners?apiVersion=2022-11-28#create-a-registration-token-for-a-repository
./config.sh --url ... --token ...

# See https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/configure-the-application
sudo ./svc.sh install
sudo ./svc.sh start

# You can follow logs with
sudo journalctl -fu actions.runner.PlanktoScope-PlanktoScope.raspberrypi.service

# See also https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/monitor-and-troubleshoot
```

See [Monitoring and troubleshooting self-hosted runners](https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/monitor-and-troubleshoot)

If you need to debug CI, the repo clone is at `~/actions-runner/_work/PlanktoScope/PlanktoScope`.

Use `sudo -E rpi-eeprom-config --edit` to set

```sh
POWER_OFF_ON_HALT=0
WAIT_FOR_POWER_BUTTON=0
```
