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

# ============== ADJUST THESE VALUES ==============
# These can probably be improved, but it works nicely around 2 bubbles a second.
RAMP_VALUES = [0.275, 0.265, 0.265, 0.275]  # Current levels to ramp through
RAMP_STEP_TIME = 0.1  # Seconds at each level
PAUSE_TIME = 0.2  # Seconds to pause (off) between cycles
# =================================================

ramp_task = None


async def start() -> None:
    # There is no GPIO bubbler on PlanktoScope HAT < 3.3
    # only USB powered bubbler
    if (await helpers.get_hat_version()) != 3.3:
        sys.exit()

    global bubbler
    import MCP4725 as bubbler

    bubbler.init(address=0x60)
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
        await on()
    elif action == "off":
        await off()
    # elif action == "settings":
    #     await handle_settings(payload)
    elif action == "save":
        if hasattr(bubbler, "save"):
            bubbler.save()


# async def handle_settings(payload) -> None:
#     assert bubbler is not None

#     if "current" in payload["settings"]:
#         # {"settings":{"current":"20"}}
#         current = payload["settings"]["current"]
#         if bubbler.is_on():
#             return
#         bubbler.set_current(current)


async def on() -> None:
    global ramp_task
    assert bubbler is not None

    if ramp_task:
        ramp_task.cancel()
        try:
            await ramp_task
        except asyncio.CancelledError:
            pass
        ramp_task = None

    # Start ramp mode
    ramp_task = asyncio.create_task(run_ramp())
    await publish_status()


async def run_ramp():
    """Ramp up through values at the top, ramp down, pause, repeat."""
    assert bubbler is not None
    try:
        while True:
            # Ramp up
            for v in RAMP_VALUES:
                bubbler.set_value(v)
                await asyncio.sleep(RAMP_STEP_TIME)
            # Ramp down
            for v in reversed(RAMP_VALUES[:-1]):
                bubbler.set_value(v)
                await asyncio.sleep(RAMP_STEP_TIME)
            # Off and pause
            bubbler.set_value(0)
            await asyncio.sleep(PAUSE_TIME)
    except asyncio.CancelledError:
        pass


async def off() -> None:
    global ramp_task
    if ramp_task:
        ramp_task.cancel()
        try:
            await ramp_task
        except asyncio.CancelledError:
            pass
        ramp_task = None
    assert bubbler is not None
    bubbler.off()
    await publish_status()


async def publish_status() -> None:
    assert bubbler is not None
    assert client is not None

    value = bubbler.get_value()

    payload = {
        "status": "Off" if bubbler.is_off() else "On",
        "value": value,
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
