import asyncio
import json
import signal
import sys
from pprint import pprint

import aiomqtt  # type: ignore

import helpers

client = None
loop = asyncio.new_event_loop()
bubbler = None
state_value = 0

# Calibrated configuration
DAC_MIN_START = 1114 # Value at 25%
DAC_MAX_POWER = 1433 # Value at 100%
KICKSTART_DURATION = 0.1 # 100ms to overcome inertia

# Translate a normalized value 0-1 to a DAC value with a special calibration : 0.25 -> 0.272, 1.0 -> 0.350.
def map_value_to_dac(value: float) -> int:
    value = max(0.0, min(value, 1.0))

    # For values between 1% and 24% (e.g. via slider)
    # we slowly increase between 0 and DAC_MIN_START
    if value < 0.25:
        dac = (value / 0.25) * DAC_MIN_START
    # Strict linear interpolation for range [25% - 100%]
    # At 25%, the right hand side is 0, we've got DAC_MIN_START
    # At 100%, the fraction equals 1, we've got DAC_MAX_POWER
    else:
        dac = DAC_MIN_START + ((value - 0.25) / 0.75) * (DAC_MAX_POWER - DAC_MIN_START)

    return int(round(max(0, min(dac, DAC_MAX_POWER))))

# Reverse of map_value_to_dac
def map_dac_to_value(dac: int) -> float:
    dac = max(0, min(dac, DAC_MAX_POWER))

    if dac < DAC_MIN_START:
        value = (dac / DAC_MIN_START) * 0.25
    else:
        value = 0.25 + ((dac - DAC_MIN_START) / (DAC_MAX_POWER - DAC_MIN_START)) * 0.75

    return max(0.0, min(value, 1.0))

async def start() -> None:
    # There is no GPIO bubbler on PlanktoScope HAT < 3.3
    # only USB powered bubbler
    if (await helpers.get_hat_version()) != 3.3:
        sys.exit()

    global bubbler
    import MCP4725 as bubbler

    bubbler.init(address=0x60)
    global state_value
    # Restore value from DAC
    state_value = map_dac_to_value(bubbler.get_raw_value())

    global client
    client = aiomqtt.Client(hostname="localhost", port=1883, protocol=aiomqtt.ProtocolVersion.V5)
    task_group = asyncio.TaskGroup()
    async with client, task_group:
        _ = await asyncio.gather(
            client.subscribe("actuator/bubbler"),
            publish_status(),
        )
        async for message in client.messages:
            task_group.create_task(handle_message(message))


async def handle_message(message) -> None:
    if not message.topic.matches("actuator/bubbler"):
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
    assert bubbler is not None

    if action == "on":
        await on(payload)
    elif action == "off":
        await off()
    elif action == "save":
        await save()

async def on(payload) -> None:
    assert bubbler is not None
    value = payload.get("value", 1)
    value = max(0.0, min(value, 1))

    if value == 0:
        await off()
        return

    global state_value
    state_value = value

    # If pump was off, kickstart
    if value >= 0.25 and bubbler.is_off():
        bubbler.set_raw_value(DAC_MAX_POWER) # Kickstart with max power
        await asyncio.sleep(KICKSTART_DURATION)

    bubbler.set_raw_value(map_value_to_dac(value))
    await publish_status()


async def off() -> None:
    assert bubbler is not None
    bubbler.off()
    global state_value
    state_value = 0
    await publish_status()

async def save() -> None:
    bubbler.save()

async def publish_status() -> None:
    assert bubbler is not None
    assert client is not None

    payload = {
        "status": "Off" if bubbler.is_off() else "On",
        "value": state_value,
    }
    await client.publish(topic="status/bubbler", payload=json.dumps(payload), retain=True)


async def stop() -> None:
    assert bubbler is not None
    await off()
    bubbler.deinit()
    loop.stop()


for s in (signal.SIGINT, signal.SIGTERM):
    loop.add_signal_handler(s, lambda: asyncio.ensure_future(stop()))


def main():
    loop.run_until_complete(start())


if __name__ == "__main__":
    main()
