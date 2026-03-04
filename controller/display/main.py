import asyncio
import json

# import logging
import os
import signal
import sys
from pprint import pprint

import aiomqtt  # type: ignore
from PIL import Image, ImageDraw, ImageFont, ImageOps  # type: ignore

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

epd = None
fontsmall = ImageFont.truetype(os.path.join(picdir, "Font.ttc"), 18)
fontnormal = ImageFont.truetype(os.path.join(picdir, "Font.ttc"), 19)
fontbig = ImageFont.truetype(os.path.join(picdir, "Font.ttc"), 22)
image = None
draw = None
epd2in9_V2 = None

logo = Image.open(os.path.join(dirname, "fairscope.bmp"))
logo_inverted = ImageOps.invert(logo.convert("L")).convert("1")

width = None
height = None


BAR_HEIGHT = 30


def drawURL(url):
    assert draw is not None
    assert width is not None
    assert height is not None
    # White bar across the bottom, black text (partial-refresh friendly)
    draw.rectangle((0, height - BAR_HEIGHT, width, height), fill=255)
    draw.text(
        (width // 2, height - BAR_HEIGHT // 2), text=url, anchor="mm", font=fontnormal, fill=0
    )


def drawHostname(hostname):
    assert width is not None
    assert height is not None
    assert draw is not None
    # White bar across the top, black text (partial-refresh friendly)
    draw.rectangle((0, 0, width, BAR_HEIGHT), fill=255)
    draw.text((width // 2, BAR_HEIGHT // 2 + 2), text=hostname, anchor="mm", font=fontbig, fill=0)


def drawBrand():
    assert width is not None
    assert height is not None
    assert image is not None
    assert draw is not None
    # Black center area between the white bars
    middle_top = BAR_HEIGHT
    middle_bottom = height - BAR_HEIGHT
    draw.rectangle((0, middle_top, width, middle_bottom), fill=0)
    # Paste inverted logo (white on black) centered
    middle_h = middle_bottom - middle_top
    x = (width - logo_inverted.width) // 2
    y = middle_top + (middle_h - logo_inverted.height) // 2
    image.paste(logo_inverted, (x, y))


def init_display(url="", hostname=""):
    """Full refresh to establish a clean baseline. Used once at startup."""
    assert epd is not None
    assert width is not None
    assert height is not None

    global image, draw
    image = Image.new("1", (width, height), 255)
    draw = ImageDraw.Draw(image)

    drawHostname(hostname)
    drawBrand()
    drawURL(url)

    epd.init()
    epd.Clear(0xFF)
    epd.display_Base(epd.getbuffer(image))
    epd.sleep()


def update_url(url):
    """Partial refresh to update only the bottom bar. No full screen flash."""
    assert epd is not None
    assert draw is not None

    drawURL(url)

    epd.init()
    epd.display_Partial(epd.getbuffer(image))
    epd.sleep()


def update_hostname(hostname):
    """Partial refresh to update only the top bar. No full screen flash."""
    assert epd is not None
    assert draw is not None

    drawHostname(hostname)

    epd.init()
    epd.display_Partial(epd.getbuffer(image))
    epd.sleep()


def render(url="", hostname=""):
    """Partial refresh to update both bars. No full screen flash."""
    assert epd is not None
    assert draw is not None
    assert width is not None
    assert height is not None

    drawHostname(hostname)
    drawURL(url)

    epd.init()
    epd.display_Partial(epd.getbuffer(image))
    epd.sleep()


async def configure(config):
    url = config.get("url", "")
    machine_name = config.get("machine-name", "")
    render(url, machine_name)


def render_off(hostname=""):
    """Full refresh with inverted colors to indicate power off."""
    assert epd is not None
    assert draw is not None
    assert width is not None
    assert height is not None
    assert image is not None

    # Black bar across the top, white hostname
    draw.rectangle((0, 0, width, BAR_HEIGHT), fill=0)
    draw.text((width // 2, BAR_HEIGHT // 2 + 2), text=hostname, anchor="mm", font=fontbig, fill=255)

    # White center with black logo (original, non-inverted)
    middle_top = BAR_HEIGHT
    middle_bottom = height - BAR_HEIGHT
    draw.rectangle((0, middle_top, width, middle_bottom), fill=255)
    middle_h = middle_bottom - middle_top
    x = (width - logo.width) // 2
    y = middle_top + (middle_h - logo.height) // 2
    image.paste(logo, (x, y))

    # Black bar across the bottom, white "OFF"
    draw.rectangle((0, height - BAR_HEIGHT, width, height), fill=0)
    draw.text(
        (width // 2, height - BAR_HEIGHT // 2), text="OFF", anchor="mm", font=fontnormal, fill=255
    )

    epd.init()
    epd.display_Base(epd.getbuffer(image))
    epd.sleep()


async def clear():
    assert epd is not None
    assert width is not None
    assert height is not None

    global image, draw
    image = Image.new("1", (width, height), 255)
    draw = ImageDraw.Draw(image)

    epd.init()
    epd.Clear(0xFF)
    epd.display_Base(epd.getbuffer(image))
    epd.sleep()


async def start() -> None:
    # There is no display on PlanktoScope HAT < 3.3
    if (await helpers.get_hat_version()) != 3.3:
        sys.exit()

    global epd, epd2in9_V2, width, height
    from waveshare_epd import epd2in9_V2  # type: ignore

    epd = epd2in9_V2.EPD()
    # horizontal
    width = epd.height
    height = epd.width

    url = "http://192.168.4.1"
    machine_name = helpers.get_machine_name()
    init_display(url=url, hostname=machine_name)

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

    payload = json.loads(message.payload.decode("utf-8"))
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
        machine_name = helpers.get_machine_name()
        render_off(hostname=machine_name)
    loop.stop()


for s in (signal.SIGINT, signal.SIGTERM):
    loop.add_signal_handler(s, lambda: asyncio.ensure_future(stop()))


def main():
    loop.run_until_complete(start())


if __name__ == "__main__":
    main()
