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
    # elif action == "settings":
    #     await handle_settings(payload)
    elif action == "save":
        if hasattr(led, "save"):
            led.save()


# async def handle_settings(payload) -> None:
#     assert led is not None

#     if "current" in payload["settings"]:
#         # {"settings":{"current":"20"}}
#         current = payload["settings"]["current"]
#         if led.is_on():
#             return
#         led.set_current(current)


async def on(payload) -> None:
    assert led is not None
    value = payload.get("value", 1)
    assert 0.0 <= value <= 1.0

    if value == 0:
        await off()
        return

    global chronometer
    if chronometer is None:
        chronometer = int(time.time())

    led.on()
    led.set_value(value)

    await publish_status()


async def off() -> None:
    assert led is not None
    led.off()

    await publish_status()

    try:
        await save_operating_time()
    except Exception as e:
        print(e)


async def publish_status() -> None:
    assert client is not None
    assert led is not None

    value = led.get_value()

    payload = {"status": "Off" if led.is_off() else "On", "value": value}
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
