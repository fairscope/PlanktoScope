import asyncio
import json
import signal
from pprint import pprint

import aiomqtt

import helpers
from motor.motor import Motor

"""Step forward"""
FORWARD = 1
""""Step backward"""
BACKWARD = 2

pump_steps_per_ml = None
pump_max_speed = None

# TMC5160 velocity conversion factor
# The TMC5160 uses internal velocity units: actual_velocity = VMAX * (fCLK / 2^24)
# With internal oscillator (~12 MHz), we need to multiply desired speed by 2^24/fCLK
TMC5160_VELOCITY_FACTOR = 1.398

pump_started = False

pump_stepper = Motor(pin=23, spi_bus=0, spi_device=0)
pump_stepper.acceleration = 2000
pump_stepper.deceleration = pump_stepper.acceleration

client = None
loop = asyncio.new_event_loop()


async def start() -> None:
    global pump_steps_per_ml, pump_max_speed, client

    hardware_config = None
    try:
        hardware_config = await helpers.read_hardware_config()
    except FileNotFoundError:
        return None

    pump_steps_per_ml = hardware_config.get("pump_steps_per_ml")
    pump_max_speed = hardware_config.get("pump_max_speed")

    if pump_steps_per_ml is None or pump_max_speed is None:
        return None

    pump_stepper.speed = int(
        pump_max_speed * pump_steps_per_ml * 256 / 60 * TMC5160_VELOCITY_FACTOR
    )

    client = aiomqtt.Client(hostname="localhost", port=1883, protocol=aiomqtt.ProtocolVersion.V5)
    task_group = asyncio.TaskGroup()
    async with client, task_group:
        _ = await asyncio.gather(
            client.subscribe("actuator/pump"),
            # publish_status(),
        )
        async for message in client.messages:
            task_group.create_task(handle_message(message))


async def handle_message(message) -> None:
    if not message.topic.matches("actuator/pump"):
        return

    payload = None
    try:
        payload = json.loads(message.payload.decode("utf-8"))
        assert isinstance(payload, dict)
    except Exception:
        return
    pprint(payload)

    action = payload.get("action")
    response = None
    if action is not None:
        response = await handle_action(action, payload)

    if client is not None:
        await helpers.mqtt_reply(client, message, response)


async def handle_action(action: str, payload) -> dict | None:
    if action == "move":
        await startPump(payload)
    elif action == "stop":
        await stopPump()
    elif action == "set-configuration":
        await setConfiguration(payload)
    elif action == "get-configuration":
        return await getConfiguration()


async def startPump(payload: dict) -> None:
    direction = None
    volume = None
    flowrate = None

    try:
        direction = payload["direction"]
        volume = float(payload["volume"])
        flowrate = float(payload["flowrate"])
    except Exception:
        # FIXME: add error handling
        return

    if flowrate == 0:
        # FIXME: add error handling
        return

    await pump(direction, volume, flowrate)


async def pump(direction: str, volume: float, flowrate: float):
    assert pump_steps_per_ml is not None
    assert pump_max_speed is not None
    global pump_started

    """Moves the pump stepper

    Args:
        direction (string): direction of the pumping
        volume (float): volume to pump, in mL
        speed (float): speed of pumping, in mL/min. Defaults to pump_max_speed.
    """

    # Validation of inputs
    if direction not in ["FORWARD", "BACKWARD"]:
        # FIXME: add error handling
        return

    # TMC5160 is configured for 256 microsteps
    nb_steps = round(pump_steps_per_ml * volume * 256)
    if flowrate > pump_max_speed:
        flowrate = pump_max_speed
    steps_per_second = flowrate * pump_steps_per_ml * 256 / 60
    pump_stepper.speed = int(steps_per_second * TMC5160_VELOCITY_FACTOR)

    pump_started = True
    if direction == "FORWARD":
        pump_stepper.go(FORWARD, nb_steps)
    elif direction == "BACKWARD":
        pump_stepper.go(BACKWARD, nb_steps)

    if client is not None:
        await client.publish(
            topic="status/pump",
            payload=json.dumps({"status": "Started", "duration": nb_steps / steps_per_second}),
            retain=True,
        )

    # FIXME: We should NOT poll spi
    # instead we should configure DIAG0 or DIAG1
    # to change state when the motor is at at goal
    # see https://github.com/PlanktoScope/PlanktoScope/issues/836
    while not await asyncio.to_thread(pump_stepper.at_goal):
        await asyncio.sleep(0.01)

    pump_started = False
    pump_stepper.release()

    if client is not None:
        await client.publish(
            topic="status/pump", payload=json.dumps({"status": "Done"}), retain=True
        )


async def stopPump() -> None:
    global pump_started
    pump_stepper.shutdown()
    pump_started = False
    if client is not None:
        await client.publish(
            topic="status/pump", payload=json.dumps({"status": "Interrupted"}), retain=True
        )


async def getConfiguration() -> dict:
    return {"pump_steps_per_ml": pump_steps_per_ml}


async def setConfiguration(config: dict) -> None:
    steps_per_ml = config.get("pump_steps_per_ml")
    # FIXME: add error handling
    if steps_per_ml is None:
        return

    await helpers.update_hardware_config({"pump_steps_per_ml": steps_per_ml})

    global pump_steps_per_ml
    pump_steps_per_ml = steps_per_ml


async def stop() -> None:
    await stopPump()
    loop.stop()


for s in (signal.SIGINT, signal.SIGTERM):
    loop.add_signal_handler(s, lambda: asyncio.ensure_future(stop()))


def main():
    loop.run_until_complete(start())


if __name__ == "__main__":
    main()
