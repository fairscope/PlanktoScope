import asyncio
import json
import math
import signal
import sys
import time
from pprint import pprint

import aiomqtt  # type: ignore

import helpers

client = None
loop = asyncio.new_event_loop()
bubbler = None

# ============== ADJUST THESE VALUES ==============
# La moyenne exacte entre ton Peak (0.275) et ta Valley (0.265)
OSCILLATION_AVERAGE = 0.264

# L'amplitude pour atteindre exactement tes limites
# 0.270 + 0.005 = 0.275 (Peak)
# 0.270 - 0.005 = 0.265 (Valley)
OSCILLATION_AMPLITUDE = 0.005

# Vitesse de l'oscillation en Hertz (cycles par seconde).
# 5.0 correspond à ton ancien cycle de 0.2 seconde.
OSCILLATION_FREQUENCY = 4

# Fréquence de mise à jour du DAC (en secondes).
# 0.01 offre une courbe très fluide à 100fps.
UPDATE_INTERVAL = 0.02
# =================================================

oscillation_task = None


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
    global oscillation_task
    assert bubbler is not None

    if oscillation_task:
        oscillation_task.cancel()
        try:
            await oscillation_task
        except asyncio.CancelledError:
            pass
        oscillation_task = None

    # Kick-start: high intensity to prime the pump
    bubbler.set_value(0.275)
    await asyncio.sleep(2)

    # Start oscillation mode
    oscillation_task = asyncio.create_task(run_oscillate())
    await publish_status()


async def run_oscillate():
    """Smoothly oscillate current using a sine wave to pulse the bubbler."""
    assert bubbler is not None
    start_time = time.time()
    try:
        while True:
            # Calculate elapsed time
            t = time.time() - start_time

            # Generate sine wave value between -1 and 1
            sine_wave = math.sin(2 * math.pi * OSCILLATION_FREQUENCY * t)

            # Scale to our desired amplitude and shift to our average
            current_val = OSCILLATION_AVERAGE + (OSCILLATION_AMPLITUDE * sine_wave)

            # Safety clamp to ensure we never pass invalid values to the DAC
            current_val = max(0.0, min(1.0, current_val))

            bubbler.set_value(current_val)

            await asyncio.sleep(UPDATE_INTERVAL)
    except asyncio.CancelledError:
        pass


async def off() -> None:
    global oscillation_task
    if oscillation_task:
        oscillation_task.cancel()
        try:
            await oscillation_task
        except asyncio.CancelledError:
            pass
        oscillation_task = None
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
