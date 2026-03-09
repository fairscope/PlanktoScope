import asyncio
import json
import signal
from pprint import pprint

import aiofiles
import aiomqtt

import helpers
from motor.motor import Motor

"""Step forward"""
FORWARD = 1
""""Step backward"""
BACKWARD = 2

# https://github.com/PlanktoScope/PlanktoScope/issues/691
focus_steps_per_mm = 27
# focus max speed is in mm/sec and is limited by the maximum number of pulses per second the PlanktoScope can send
focus_max_speed = 5

focus_started = False

focus_stepper = Motor(pin=5, spi_bus=0, spi_device=1)
focus_stepper.acceleration = 1000
focus_stepper.deceleration = focus_stepper.acceleration

client = None
loop = asyncio.new_event_loop()


async def start() -> None:
    global focus_steps_per_mm, focus_max_speed, client

    hardware_config = None
    try:
        async with aiofiles.open("/home/pi/PlanktoScope/hardware.json", mode="r") as file:
            hardware_config = json.loads(await file.read())
    except FileNotFoundError:
        return None

    if hardware_config is not None:
        # parse the config data. If the key is absent, we are using the default value
        focus_steps_per_mm = hardware_config.get("focus_steps_per_mm", focus_steps_per_mm)
        focus_max_speed = hardware_config.get("focus_max_speed", focus_max_speed)

    focus_stepper.speed = focus_max_speed * focus_steps_per_mm * 256

    client = aiomqtt.Client(hostname="localhost", port=1883, protocol=aiomqtt.ProtocolVersion.V5)
    task_group = asyncio.TaskGroup()
    async with client, task_group:
        _ = await asyncio.gather(
            client.subscribe("actuator/focus"),
            # publish_status(),
        )
        async for message in client.messages:
            task_group.create_task(handle_message(message))


async def handle_message(message) -> None:
    if not message.topic.matches("actuator/focus"):
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
    if action == "move":
        await startFocus(payload)
    elif action == "stop":
        await stopFocus()


async def startFocus(payload) -> None:
    direction = None
    distance = None
    speed = None

    try:
        direction = payload["direction"]
        distance = float(payload["distance"])
        speed = float(payload["speed"] if "speed" in payload else focus_max_speed)
    except Exception:
        # FIXME: add error handling
        return

    await focus(direction, distance, speed)


async def focus(direction: str, distance: float, speed: float = focus_max_speed):
    global focus_started

    """Moves the focus stepper

    direction is either UP or DOWN
    distance is received in mm
    speed is in mm/sec

    Args:
        direction (string): either UP or DOWN
        distance (float): distance to move the stage, in mm
        speed (float, optional): max speed of the stage, in mm/sec. Defaults to focus_max_speed.
    """

    # Validation of inputs
    if direction not in ["UP", "DOWN"]:
        # FIXME: add error handling
        return

    # Stage physical size
    if distance > 45:
        # FIXME: add error handling
        return

    # We are going to use 256 microsteps, so we need to multiply by 256 the steps number
    nb_steps = round(focus_steps_per_mm * distance * 256)
    if speed > focus_max_speed:
        speed = focus_max_speed
    steps_per_second = speed * focus_steps_per_mm * 256
    focus_stepper.speed = int(steps_per_second)

    focus_started = True
    if direction == "UP":
        focus_stepper.go(FORWARD, nb_steps)
    elif direction == "DOWN":
        focus_stepper.go(BACKWARD, nb_steps)

    if client is not None:
        await client.publish(
            topic="status/focus",
            payload=json.dumps({"status": "Started", "duration": nb_steps / steps_per_second}),
            retain=True,
        )

    # FIXME: We should NOT poll spi
    # instead we should configure DIAG0 or DIAG1
    # to change state when the motor is at at goal
    # see https://github.com/PlanktoScope/PlanktoScope/issues/836
    while not await asyncio.to_thread(focus_stepper.at_goal):
        await asyncio.sleep(0.01)

    focus_started = False
    focus_stepper.release()

    if client is not None:
        await client.publish(
            topic="status/focus", payload=json.dumps({"status": "Done"}), retain=True
        )


async def stopFocus() -> None:
    global focus_started
    focus_stepper.shutdown()
    focus_started = False
    if client is not None:
        await client.publish(
            topic="status/focus", payload=json.dumps({"status": "Interrupted"}), retain=True
        )


async def stop() -> None:
    await stopFocus()
    loop.stop()


for s in (signal.SIGINT, signal.SIGTERM):
    loop.add_signal_handler(s, lambda: asyncio.ensure_future(stop()))


def main():
    loop.run_until_complete(start())


if __name__ == "__main__":
    main()
