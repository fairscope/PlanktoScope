import asyncio
import json
import socket
from typing import Any, cast

import aiofiles
import aiomqtt
import paho

HARDWARE_CONFIG_PATH = "/home/pi/PlanktoScope/hardware.json"
hardwre_config_lock = asyncio.Lock()


async def read_hardware_config() -> dict[str, Any]:
    async with aiofiles.open(HARDWARE_CONFIG_PATH, "r") as f:
        content = await f.read()
        return cast(dict[str, Any], json.loads(content))


async def write_hardware_config(data: dict[str, Any]) -> None:
    async with aiofiles.open(HARDWARE_CONFIG_PATH, "w") as f:
        await f.write(json.dumps(data, indent=2))


async def update_hardware_config(updates: dict[str, Any]) -> None:
    async with hardwre_config_lock:
        data = await read_hardware_config()
        data.update(updates)
        await write_hardware_config(data)


async def get_hat_version() -> float | None:
    try:
        hardware = await read_hardware_config()
        hat_version = hardware.get("hat_version")
        if hat_version is None:
            return None
        else:
            return float(hat_version)
    except FileNotFoundError:
        return None


async def mqtt_reply(
    client: aiomqtt.Client, message: aiomqtt.Message, response: dict[str, Any] | None = {}
) -> None:
    response_topic = getattr(message.properties, "ResponseTopic", None)
    if response_topic is None:
        return

    correlation_data = getattr(message.properties, "CorrelationData", None)
    properties = paho.mqtt.properties.Properties(paho.mqtt.packettypes.PacketTypes.PUBLISH)

    if correlation_data is not None:
        properties.CorrelationData = correlation_data

    await client.publish(
        topic=response_topic,
        payload=json.dumps(response),
        qos=1,
        properties=properties,
        retain=False,
    )


def get_machine_name():
    hostname = socket.gethostname()
    return hostname.removeprefix("planktoscope-")
