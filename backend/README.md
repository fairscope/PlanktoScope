# backend

APIs and service for the PlanktoScope frontend.

### Development

Install all dependencies including development tooling:

```sh
cd backend
just setup-dev
```

Start service for development:

```sh
just dev
```

Run the code auto-formatter on the project:

```sh
just format
```

Run all checks (including code formatting and linting):

```sh
just test
```

## Notes

See https://github.com/raspberrypi/utils/blob/master/eeptools

```sh
eepmake eeprom_settings.txt planktoscope-hat.eep

# write
sudo gpioset -m signal gpiochip0 26=0 # disable write protect
sudo eepflash.sh --yes --write --type=24c32 --address=50 --file=planktoscope-hat.eep
ee

# read
sudo eepflash.sh --yes --read --type=24c32 --address=50 --file=dump.eep
eepdump dump.eep dump.txt
```
