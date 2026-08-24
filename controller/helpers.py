import asyncio
import json
import os
import socket
import tempfile
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


def _write_hardware_config_atomic(data: dict[str, Any]) -> None:
    """Replace hardware.json in one step.

    Several controller processes persist calibration here (pump, light, imager), and a
    partially written hardware.json leaves the instrument unbootable, so the new contents
    go to a temporary file in the same directory and are then renamed over the old one.
    `os.replace` is atomic within a filesystem, so a reader sees either the old file or the
    new one and never a truncated one.
    """
    directory = os.path.dirname(HARDWARE_CONFIG_PATH)
    fd, tmp_path = tempfile.mkstemp(dir=directory, prefix=".hardware.json.")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(json.dumps(data, indent=2))
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, HARDWARE_CONFIG_PATH)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


async def write_hardware_config(data: dict[str, Any]) -> None:
    await asyncio.to_thread(_write_hardware_config_atomic, data)


async def update_hardware_config(updates: dict[str, Any]) -> None:
    async with hardwre_config_lock:
        data = await read_hardware_config()
        data.update(updates)
        await write_hardware_config(data)


def read_hardware_config_sync() -> dict[str, Any]:
    """Blocking counterpart of `read_hardware_config`, for threaded services."""
    with open(HARDWARE_CONFIG_PATH, "r") as f:
        return cast(dict[str, Any], json.load(f))


def update_hardware_config_sync(updates: dict[str, Any]) -> None:
    """Blocking counterpart of `update_hardware_config`, for threaded services.

    The imager runs on threads rather than asyncio, so it cannot take the asyncio lock
    above. That lock only ever served to serialize writers inside a single process anyway
    — pump, light and imager are separate processes — and the atomic replace is what
    actually protects the file.
    """
    data = read_hardware_config_sync()
    data.update(updates)
    _write_hardware_config_atomic(data)


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
