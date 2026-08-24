import adafruit_mcp4725  # type: ignore
import board  # type: ignore
import busio  # type: ignore

# Proportional 0 to VOLTAGE_MAX
DAC_MIN = 0
DAC_MAX = 4095

# at 3.3V the output range is 0-3300mV
# at 5V the output range is 0-5000mV
VOLTAGE_MIN = 0
VOLTAGE_MAX = 5000  # mV

i2c = None
dac = None

# Level `on()` restores, in raw DAC counts. `off()` drives the output to zero but leaves
# this alone, so switching the LED back on returns it to the brightness it was last set to
# rather than to full scale.
_level = DAC_MAX


def map_to_voltage(value):
    return (value / DAC_MAX) * VOLTAGE_MAX


def map_to_value(voltage):
    return int((voltage / VOLTAGE_MAX) * DAC_MAX)


def on() -> None:
    assert dac is not None
    # Deliberately not DAC_MAX: driving the LED to full scale here made every switch-on
    # flash at maximum brightness before the caller set the requested level.
    dac.raw_value = _level


def off() -> None:
    assert dac is not None
    dac.raw_value = DAC_MIN


def save() -> None:
    assert dac is not None
    dac.save_to_eeprom()


def is_on() -> bool:
    return not is_off()


def is_off() -> bool:
    assert dac is not None
    return dac.raw_value == DAC_MIN


def init(address: int) -> None:
    global i2c, dac
    i2c = busio.I2C(board.SCL, board.SDA)
    dac = adafruit_mcp4725.MCP4725(i2c, address=address)
    dac.raw_value = 0


def deinit() -> None:
    if i2c is not None:
        i2c.deinit()


def get_value() -> float:
    assert dac is not None
    return float(dac.normalized_value)


def set_value(value: float) -> None:
    global _level
    assert dac is not None
    dac.normalized_value = value
    if dac.raw_value > DAC_MIN:
        _level = dac.raw_value


def get_raw_value() -> int:
    assert dac is not None
    return int(dac.raw_value)


def set_raw_value(value: int) -> None:
    global _level
    assert dac is not None
    dac.raw_value = value
    if value > DAC_MIN:
        _level = value
