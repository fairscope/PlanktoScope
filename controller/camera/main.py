import json
import sys
import loguru
import typing

from . import mqtt as camera

_camera = None

def read_config() -> typing.Any:
    config = {}
    try:
        with open("/home/pi/PlanktoScope/hardware.json", "r") as file:
            try:
                config = json.load(file)
            except Exception:
                return None
    except Exception:
        return None

    return config

def main():
    loguru.logger.info("Starting the camera...")
    _camera = camera.Worker(read_config())
    _camera.start()
    if _camera.camera is None:
        sys.exit()

if __name__ == "__main__":
    main()
