import enum
import json

import smbus2 as smbus
from gpiozero import DigitalOutputDevice  # type: ignore[attr-defined]


class i2c_led:
    """
    LM36011 Led controller
    """

    @enum.unique
    class Register(enum.IntEnum):
        enable = 0x01
        configuration = 0x02
        flash = 0x03
        torch = 0x04
        flags = 0x05
        id_reset = 0x06

    DEVICE_ADDRESS = 0x64
    # This constant defines the current (mA) sent to the LED, 10 allows the use of the full ISO scale and results in a voltage of 2.77v
    DEFAULT_CURRENT = 10
    # The torch brightness register is 7 bits wide (bit 7 is reserved), so the
    # usable range is 0-127: ~2.4 mA at 0 up to ~376 mA at 127.
    TORCH_MAX = 127

    def __init__(self):
        with open("/home/pi/PlanktoScope/hardware.json", "r") as file:
            config = json.load(file)
            hat_version = float(config.get("hat_version") or 0)
            # The led is controlled by LM36011
            # but on version 1.2 of the PlanktoScope HAT (PlanktoScope v2.6)
            # the circuit is connected to the pin 18 so it needs to be high
            # pin is assigned to self to prevent gpiozero from immediately releasing it
            if hat_version < 3.2:
                self.__pin = DigitalOutputDevice(pin=18, initial_value=True)

        self.VLED_short = False
        self.thermal_scale = False
        self.thermal_shutdown = False
        self.UVLO = False
        self.flash_timeout = False
        self.IVFM = False
        self.on = False
        self.force_reset()
        if self.get_flags():
            self.VLED_short = False
            self.thermal_scale = False
            self.thermal_shutdown = False
            self.UVLO = False
            self.flash_timeout = False
            self.IVFM = False
        self.led_id = self.get_id()

    def get_id(self):
        led_id = self._read_byte(self.Register.id_reset)
        led_id = led_id & 0b111111
        return led_id

    def get_state(self):
        return self.on

    def activate_torch_ramp(self):
        reg = self._read_byte(self.Register.configuration)
        reg = reg | 0b1
        self._write_byte(self.Register.configuration, reg)

    def deactivate_torch_ramp(self):
        reg = self._read_byte(self.Register.configuration)
        reg = reg | 0b0
        self._write_byte(self.Register.configuration, reg)

    def force_reset(self):
        self._write_byte(self.Register.id_reset, 0b10000000)

    def get_flags(self):
        flags = self._read_byte(self.Register.flags)
        self.flash_timeout = bool(flags & 0b1)
        self.UVLO = bool(flags & 0b10)
        self.thermal_shutdown = bool(flags & 0b100)
        self.thermal_scale = bool(flags & 0b1000)
        self.VLED_short = bool(flags & 0b100000)
        self.IVFM = bool(flags & 0b1000000)
        return flags

    def set_torch_current(self, current):
        # From 3 to 376mA
        # Curve is not linear for some reason, but this is close enough
        if current > 376:
            raise ValueError("the chosen current is too high, max value is 376mA")
        value = int(current * 0.34)
        self._write_byte(self.Register.torch, value)

    def set_torch_value(self, value: int) -> None:
        """Write the torch brightness register directly, in native 0-127 units.

        Prefer this over `set_torch_current` when the caller wants brightness
        rather than a specific current: going through mA quantises the range
        twice (mA * 0.34 collapses 0-20 down to just 7 distinct register
        values), which is what made lightness 230 unreachable on v2.6.
        """
        self._write_byte(self.Register.torch, self._clamp_torch(value))

    def get_torch_value(self) -> int:
        # Mask off the reserved bit so a stray high bit can't report as brightness.
        # `_read_byte` is untyped, so narrow it explicitly rather than leaking Any.
        return int(self._read_byte(self.Register.torch) & self.TORCH_MAX)

    @classmethod
    def _clamp_torch(cls, value: float) -> int:
        """Clamp to the 7-bit register range; anything higher would spill into
        the reserved bit rather than getting brighter."""
        return max(0, min(int(value), cls.TORCH_MAX))

    def get_torch_current(self):
        return self._read_byte(self.Register.torch)

    def set_flash_current(self, current):
        # From 11 to 1500mA
        # Curve is not linear for some reason, but this is close enough
        value = int(current * 0.085)
        self._write_byte(self.Register.flash, value)

    def activate_torch(self):
        self._write_byte(self.Register.enable, 0b10)
        self.on = True

    def deactivate_torch(self):
        self._write_byte(self.Register.enable, 0b00)
        self.on = False

    def _write_byte(self, address, data):
        with smbus.SMBus(1) as bus:
            bus.write_byte_data(self.DEVICE_ADDRESS, address, data)

    def _read_byte(self, address):
        with smbus.SMBus(1) as bus:
            b = bus.read_byte_data(self.DEVICE_ADDRESS, address)
        return b


led = i2c_led()


def on() -> None:
    led.activate_torch()


def off() -> None:
    led.deactivate_torch()


def save() -> None:
    return


def is_on() -> bool:
    return led.on


def is_off() -> bool:
    return not is_on()


def init() -> None:
    led.set_torch_current(i2c_led.DEFAULT_CURRENT)
    led.activate_torch_ramp()


def deinit() -> None:
    led.deactivate_torch()
    led.set_torch_current(1)
    led.set_flash_current(1)


def get_value() -> float:
    # A 0-1 fraction, matching what `set_value` accepts and what the v3 MCP4725
    # driver reports. This used to divide the raw register by 20 and round to an
    # int, so `status/light` reported 0 for every register below 10.
    return led.get_torch_value() / i2c_led.TORCH_MAX


def set_value(value: float) -> None:
    # `value` is a 0-1 fraction of full brightness, mapped straight onto the
    # 7-bit torch register for the full 128 levels the LM36011 offers.
    #
    # This used to route through set_torch_current(round(value * 20)), which
    # quantised twice: 0-1 became 0-20, then mA * 0.34 collapsed that to 7
    # distinct register values (0-6). Three neighbouring slider positions all
    # produced the same current, and one step past the boundary jumped a whole
    # level — which is why lightness 230 sat unreachable between 219 and 242
    # (fairscope/PlanktoScope3#309).
    #
    # NOTE: this changes what a stored setting means. The same 0-1 value now
    # produces a much higher current than before (0.4 was register 2, it is now
    # register 50), so existing calibrations must be re-measured.
    led.set_torch_value(round(max(0.0, min(float(value), 1.0)) * i2c_led.TORCH_MAX))
    return
