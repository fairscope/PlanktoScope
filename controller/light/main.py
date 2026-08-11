import asyncio
import json
import signal
import sys
import time
from pprint import pprint

import aiomqtt  # type: ignore

import helpers

client = None
loop = asyncio.new_event_loop()
led = None
chronometer = None

# Key under which the calibrated brightness is persisted in hardware.json.
INTENSITY_CONFIG_KEY = "led_intensity"
DEFAULT_INTENSITY = 1.0

# Calibrated brightness, in the range [0, 1]. Restored from hardware.json at startup and
# used whenever the LED is switched on without an explicit value, so a reboot or an
# off/on cycle no longer costs the operator their light calibration.
intensity = DEFAULT_INTENSITY


def _clamp(value: float) -> float:
    return max(0.0, min(float(value), 1.0))


async def load_intensity() -> None:
    """Restore the calibrated brightness from hardware.json.

    A missing or malformed value is not fatal — the LED simply falls back to full
    brightness, which is the behaviour this instrument had before the value was persisted.
    """
    global intensity
    try:
        config = await helpers.read_hardware_config()
    except (OSError, ValueError) as e:
        print(f"Could not read hardware config, using default LED intensity: {e}")
        return

    stored = config.get(INTENSITY_CONFIG_KEY)
    if stored is None:
        return

    try:
        intensity = _clamp(stored)
    except (TypeError, ValueError):
        print(f"Ignoring invalid {INTENSITY_CONFIG_KEY} in hardware config: {stored!r}")


async def start() -> None:
    global led
    hat_version = await helpers.get_hat_version()
    if hat_version is None:
        sys.exit()

    if hat_version == 1.2:
        from . import LM36011 as led

        led.init()
    elif hat_version == 3.3:
        import MCP4725 as led

        led.init(address=0x62)
    else:
        raise Exception("Unknown hat_version", hat_version)

    # The LED stays off until asked to turn on; this only restores the level it will use.
    await load_intensity()

    global client
    client = aiomqtt.Client(hostname="localhost", port=1883, protocol=aiomqtt.ProtocolVersion.V5)
    task_group = asyncio.TaskGroup()
    async with client, task_group:
        _ = await asyncio.gather(
            client.subscribe("light"),
            publish_status(),
        )
        async for message in client.messages:
            task_group.create_task(handle_message(message))


async def handle_message(message) -> None:
    if not message.topic.matches("light"):
        return

    payload = None
    try:
        payload = json.loads(message.payload.decode("utf-8"))
        assert isinstance(payload, dict)
    except Exception:
        return
    pprint(payload)

    action = payload.get("action")
    if action is not None:
        await handle_action(action, payload)

    if client is not None:
        await helpers.mqtt_reply(client, message)


async def handle_action(action: str, payload) -> None:
    assert led is not None

    if action == "on":
        await on(payload)
    elif action == "off":
        await off()
    elif action == "save":
        await save()


async def on(payload) -> None:
    assert led is not None
    global intensity

    # No explicit value means "switch on as calibrated", which is what restores the
    # operator's setting after a reboot or an off/on cycle.
    requested = payload.get("value")
    value = intensity if requested is None else _clamp(requested)

    if value == 0:
        await off()
        return

    intensity = value

    global chronometer
    if chronometer is None:
        chronometer = int(time.time())

    # Set the level before enabling the output, otherwise the LED briefly lights at
    # whatever level the driver defaults to.
    led.set_value(value)
    led.on()

    await publish_status()


async def off() -> None:
    assert led is not None
    led.off()

    await publish_status()

    try:
        await save_operating_time()
    except Exception as e:
        print(e)


async def save() -> None:
    """Persist the current brightness as the calibrated one.

    hardware.json is the source of truth restored at startup. On the v3 HAT the DAC can
    also latch the level in its own EEPROM, which is kept because it makes the LED come up
    correctly even before this service starts; the v2.6 LM36011 has no EEPROM and its
    `save()` is a no-op, which is exactly why the level cannot live in hardware alone.
    """
    assert led is not None

    try:
        await helpers.update_hardware_config({INTENSITY_CONFIG_KEY: intensity})
    except (OSError, ValueError) as e:
        # A failed save must not take down the MQTT handler; the LED keeps working at the
        # requested level, it just will not survive a reboot.
        print(f"Could not persist LED intensity: {e}")
        return

    if hasattr(led, "save"):
        led.save()

    await publish_status()


async def publish_status() -> None:
    assert client is not None
    assert led is not None

    # Report the calibrated level rather than reading the hardware back. The DAC reads 0
    # whenever the LED is off, and the LM36011 rounds its torch current to whole units on
    # readback, so neither can tell the dashboard which brightness to show at startup.
    payload = {"status": "Off" if led.is_off() else "On", "value": intensity}
    await client.publish(topic="status/light", payload=json.dumps(payload), retain=True)


async def stop() -> None:
    assert led is not None
    await off()
    led.deinit()
    loop.stop()


async def save_operating_time() -> None:
    assert client is not None
    global chronometer
    if chronometer is None:
        return

    operating_time = int(time.time()) - chronometer

    payload = {
        "action": "increment",
        "seconds": operating_time,
    }
    await client.publish(topic="led-operating-time", payload=json.dumps(payload))
    chronometer = None


for s in (signal.SIGINT, signal.SIGTERM):
    loop.add_signal_handler(s, lambda: asyncio.ensure_future(stop()))


def main():
    loop.run_until_complete(start())


if __name__ == "__main__":
    main()
