import asyncio
import json

# import logging
import os
import signal
import sys
from pprint import pprint

import aiomqtt  # type: ignore
from PIL import Image, ImageDraw, ImageFont  # type: ignore

import helpers

# Hardware
# We use Waveshare 2.9inch E-Ink display module (black and white) SPI
# https://www.waveshare.com/2.9inch-e-paper-module.htm
# https://www.waveshare.com/wiki/2.9inch_e-Paper_Module

# Software
# We use the Python implementation provided by Waveshare
# https://github.com/waveshareteam/e-Paper/tree/master/RaspberryPi_JetsonNano/python/lib/waveshare_epd
# As well as Pillow to draw the image rendered to the screen
# https://pillow.readthedocs.io/en/stable/index.html
# https://pillow.readthedocs.io/en/stable/reference/ImageDraw.html
# https://pillow.readthedocs.io/en/stable/handbook/text-anchors.html

# Enable waveshare_epd logs
# logging.basicConfig(level=logging.DEBUG)

client = None
loop = asyncio.new_event_loop()

dirname = os.path.dirname(__file__)
picdir = os.path.join(dirname, "e-paper/pic")
libdir = os.path.join(dirname, "e-paper/lib")
if os.path.exists(libdir):
    sys.path.append(libdir)

machine_name = None
epd = None
fontsmall = ImageFont.truetype(os.path.join(picdir, "Font.ttc"), 18)
fontnormal = ImageFont.truetype(os.path.join(picdir, "Font.ttc"), 19)
fontbig = ImageFont.truetype(os.path.join(picdir, "Font.ttc"), 22)
image = None
draw = None
epd2in9_V2 = None

logo = Image.open(os.path.join(dirname, "fairscope.bmp"))

width = None
height = None


BAR_HEIGHT = 26


def drawStatus(status=""):
    assert draw is not None
    assert width is not None
    assert height is not None
    # Black bar across the bottom
    draw.rectangle((0, height - BAR_HEIGHT, width, height), fill=0)
    # White text centered in the bar
    draw.text(
        (width // 2, height - BAR_HEIGHT // 2), text=status, anchor="mm", font=fontnormal, fill=255
    )


def drawMachineName(machine_name):
    assert width is not None
    assert height is not None
    assert draw is not None
    # Black bar across the top
    draw.rectangle((0, 0, width, BAR_HEIGHT), fill=0)
    # White text centered in the bar
    draw.text(
        (width // 2, BAR_HEIGHT // 2 + 2), text=machine_name, anchor="mm", font=fontbig, fill=255
    )


def drawBrand():
    assert width is not None
    assert height is not None
    assert image is not None
    # Paste logo centered in the middle white area (between the two bars)
    middle_top = BAR_HEIGHT
    middle_bottom = height - BAR_HEIGHT
    middle_h = middle_bottom - middle_top
    x = (width - logo.width) // 2
    y = middle_top + (middle_h - logo.height) // 2
    image.paste(logo, (x, y))


def render(status=""):
    assert epd is not None
    assert width is not None
    assert height is not None

    global image, draw
    if image is None or draw is None:
        image = Image.new("1", (width, height), 255)
        draw = ImageDraw.Draw(image)

    # clear screen
    # # TODO: only clear relevant area ?
    draw.rectangle((0, 0, height, width), fill=255)

    # top black bar with machine_name
    drawMachineName(machine_name)
    # center logo
    drawBrand()
    # bottom black bar with status
    drawStatus(status)

    epd.init()
    epd.Clear(0xFF)

    epd.display_Base(epd.getbuffer(image))
    # epd.sleep()


async def configure(config):
    assert draw is not None
    assert width is not None
    assert height is not None
    assert epd is not None
    assert image is not None

    status = config.get("status", "")

    drawStatus(status=status)
    newimage = image.crop((0, height - BAR_HEIGHT, width, height))
    image.paste(newimage, (0, height - BAR_HEIGHT))

    epd.display_Partial(epd.getbuffer(image))


async def clear():
    assert epd is not None
    assert width is not None
    assert height is not None
    # not functional
    epd.init()
    epd.Clear(0xFF)
    epd.sleep()
    # image = Image.new("1", (width, height), 255)
    # draw = ImageDraw.Draw(image)
    # draw.rectangle((0, 0, height, width), fill=255)
    # epd.display_Partial(epd.getbuffer(image))


async def start() -> None:
    # There is no display on PlanktoScope HAT < 3.3
    if (await helpers.get_hat_version()) != 3.3:
        sys.exit()

    global epd, epd2in9_V2, width, height, machine_name
    from waveshare_epd import epd2in9_V2  # type: ignore

    epd = epd2in9_V2.EPD()
    # horizontal
    width = epd.height
    height = epd.width

    machine_name = helpers.get_machine_name()

    global client
    client = aiomqtt.Client(hostname="localhost", port=1883, protocol=aiomqtt.ProtocolVersion.V5)
    task_group = asyncio.TaskGroup()
    async with client, task_group:
        _ = await asyncio.gather(
            client.subscribe("display"),
        )

        async for message in client.messages:
            task_group.create_task(handle_message(message))


async def handle_message(message) -> None:
    if not message.topic.matches("display"):
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
    if action == "clear":
        await clear()
    if action == "configure" and "config" in payload:
        await configure(payload["config"])


async def stop() -> None:
    if epd is not None:
        render(status="OFF")
    loop.stop()


for s in (signal.SIGINT, signal.SIGTERM):
    loop.add_signal_handler(s, lambda: asyncio.ensure_future(stop()))


def main():
    loop.run_until_complete(start())


if __name__ == "__main__":
    main()
