"""mqtt provides an MQTT API for camera supervision and interaction."""

import datetime as dt
import errno
import json
import os
import threading
import time
import typing

import loguru

import mqtt as messaging

from . import hardware

loguru.logger.info("planktoscope.camera is loaded")


class Worker(threading.Thread):
    """Runs a camera with MQTT API for adjusting camera settings."""

    def __init__(
        self,
        configuration: dict[str, typing.Any],
    ) -> None:
        """Initialize the backend.

        Raises:
            ValueError: one or more values in the hardware config file are of the wrong type.
        """
        super().__init__(name="camera")

        # Settings
        settings = hardware.SettingsValues(
            auto_exposure=False,
            exposure_time=125,  # the default (minimum) exposure time in the PlanktoScope GUI
            # Note(ethanjli): an error will occur if exposure time is outside any provided frame
            # duration limits (set by explicitly defining a `frame_duration_limits` param here. In
            # practice, this means we cannot reduce the max allowed framerate below
            # 1/(125 us) = 8000 fps, for exposure time of 125 us. So we have to limit the framerate
            # some other way.
            image_gain=1.0,  # image gain is reinitialized after the image sensor is determined
            brightness=0.0,  # the default "normal" brightness
            contrast=1.0,  # the default "normal" contrast
            auto_white_balance=False,  # the default setting in the PlanktoScope GUI
            white_balance_gains=hardware.WhiteBalanceGains(
                # the default gains from the default v2.5 hardware config
                red=2.4,
                blue=1.35,
            ),
            sharpness=0,  # disable the default "normal" sharpening level
            jpeg_quality=95,  # maximize image quality
        )
        settings = settings.overlay(hardware.config_to_settings_values(configuration))

        # I/O
        self._camera: typing.Optional[hardware.PiCamera] = hardware.PiCamera(
            initial_settings=settings
        )
        self._camera_checked = threading.Event()
        self._stop_event_loop = threading.Event()

    @loguru.logger.catch
    def run(self) -> None:
        """Start the camera and run the main event loop."""
        assert self._camera is not None

        loguru.logger.info("Initializing the camera with default settings...")
        try:
            self._camera.open()
        except RuntimeError:
            loguru.logger.exception("Couldn't open the camera - maybe it's disconnected?")
            self._camera = None
            self._camera_checked.set()
            return
        self._camera_checked.set()

        default_iso = 150
        loguru.logger.debug(f"Setting camera image gain for default ISO value of {default_iso}...")
        changes = hardware.SettingsValues(image_gain=default_iso / hardware.ISO_CALIBRATION)
        try:
            _validate_settings(changes)
        except (TypeError, ValueError) as e:
            raise ValueError("Invalid default ISO") from e
        self._camera.settings = changes
        loguru.logger.debug(
            f"Set image gain to {changes.image_gain}!",
        )

        loguru.logger.info("Starting the MQTT backend...")
        mqtt = messaging.MQTT_Client(topic="imager/image", name="imager_camera_client")
        self.mqtt = mqtt

        try:
            while not self._stop_event_loop.is_set():
                if not mqtt.new_message_received():
                    time.sleep(0.1)
                    continue
                loguru.logger.debug(mqtt.msg)
                if (message := mqtt.msg) is None:
                    continue
                self._receive_message(message)
                if (status_update := mqtt.read_message()) is not None:
                    mqtt.client.publish("status/imager", status_update)
        finally:
            loguru.logger.info("Stopping the MQTT API...")
            mqtt.shutdown()

            loguru.logger.info("Stopping the camera...")
            self._camera.close()
            self._camera = None

            loguru.logger.success("Done shutting down!")

    @loguru.logger.catch
    def capture(self, payload: dict[str, typing.Any]) -> None:
        assert self._camera is not None

        picam2 = self._camera._camera
        assert picam2 is not None

        # https://datasheets.raspberrypi.com/camera/picamera2-manual.pdf
        # 6.1.4. Capturing straight to files and file-like objects
        picam2.options["quality"] = (
            95  # JPEG quality level, where 0 is the worst quality and 95 is best.
        )

        filename_basename = f"{dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d_%H-%M-%S-%f')}"
        parent = "/home/pi/data/captures"

        try:
            os.makedirs(parent)
        except OSError as e:
            if e.errno != errno.EEXIST:
                raise

        capture_path = os.path.join(parent, filename_basename)

        loguru.logger.debug(f"Capturing and saving image {filename_basename}")

        (buffer_main, buffer_raw), metadata = picam2.capture_buffers(["main", "raw"])

        loguru.logger.debug(
            f"Image metadata: {metadata}"  # pylint: disable=no-member
        )

        # TODO: The dng should have the jpeg as preview metadata
        path_dng = None
        if payload.get("dng") is True:
            path_dng = capture_path + ".dng"
            picam2.helpers.save_dng(
                buffer=buffer_raw,
                metadata=metadata,
                config=picam2.camera_configuration()["raw"],
                file_output=path_dng,
            )
            # Use fsync to ensure write completes
            with open(path_dng, "ab") as f:
                os.fsync(f.fileno())

        path_jpeg = None
        if payload.get("jpeg") is not False:
            path_jpeg = capture_path + ".jpg"
            image_main = picam2.helpers.make_image(
                buffer=buffer_main, config=picam2.camera_configuration()["main"]
            )
            picam2.helpers.save(
                img=image_main, metadata=metadata, format="jpeg", file_output=path_jpeg
            )
            # Use fsync to ensure write completes
            with open(path_jpeg, "ab") as f:
                os.fsync(f.fileno())

        assert self.mqtt
        self.mqtt.client.publish(
            "status/imager",
            json.dumps(
                {
                    "action": "capture",
                    "jpeg": path_jpeg,
                    "dng": path_dng,
                }
            ),
        )

    @loguru.logger.catch
    def _receive_message(self, message: dict[str, typing.Any]) -> typing.Optional[str]:
        """Handle a single MQTT message.

        Returns a status update to broadcast.
        """
        assert self._camera is not None

        if message["topic"] != "imager/image":
            return None

        if message["payload"].get("action", "") == "capture":
            self.capture(message["payload"])
            return None

        if message["payload"].get("action", "") != "settings":
            return None

        if "settings" not in message["payload"]:
            loguru.logger.error(f"Received message is missing field 'settings': {message}")
            return '{"status":"Camera settings error"}'

        loguru.logger.info("Updating camera settings...")
        settings = message["payload"]["settings"]
        try:
            converted_settings = _convert_settings(
                settings, self._camera.settings.white_balance_gains
            )
            _validate_settings(converted_settings)
        except (TypeError, ValueError) as e:
            loguru.logger.exception(
                f"Couldn't convert MQTT command to hardware settings: {settings}",
            )
            return json.dumps({"status": f"Error: {str(e)}"})

        self._camera.settings = converted_settings
        loguru.logger.success("Updated camera settings!")
        return '{"status":"Camera settings updated"}'

    @property
    def camera(self) -> typing.Optional[hardware.PiCamera]:
        """Return the camera wrapper managed by this worker.

        Blocks until this worker has attempted to start the camera (so this property will wait until
        this worker has been started as a thread).

        Returns:
            The camera wrapper if it started successfully, or None if the camera wrapper could not
            be started (e.g. because the camera does not exists).
        """
        self._camera_checked.wait()
        return self._camera

    def shutdown(self):
        """Stop processing new MQTT messages and gracefully stop working."""
        self._stop_event_loop.set()


def _convert_settings(
    command_settings: dict[str, typing.Any],
    default_white_balance_gains: typing.Optional[hardware.WhiteBalanceGains],
) -> hardware.SettingsValues:
    """Convert MQTT command settings to camera hardware settings.

    Args:
        command_settings: the settings to convert.
        default_white_balance_gains: white-balance gains to substitute for missing values, if
          exactly one gain was provided in `command_settings`.

    Returns:
        All settings extracted from the MQTT command.

    Raises:
        ValueError: at least one of the MQTT command settings is invalid.
    """
    # TODO(ethanjli): separate out the status from the error message in the MQTT API, so
    # that we can just directly use the error messages from the
    # `hardware.SettingsValues.validate()` method. That would be simpler; for now we're
    # trying to keep the MQTT API unchanged, so we return different ValueErrors.
    converted = hardware.SettingsValues()
    if "shutter_speed" in command_settings:
        try:
            exposure_time = int(command_settings["shutter_speed"])
        except (TypeError, ValueError) as e:
            raise ValueError("Shutter speed not valid") from e
        converted = converted._replace(exposure_time=exposure_time)
    converted = converted.overlay(
        _convert_image_gain_settings(
            command_settings,
        )
    )
    if "white_balance" in command_settings:
        if (awb := command_settings["white_balance"]) not in {"auto", "off"}:
            raise ValueError("White balance mode {awb} not valid")
        converted = converted._replace(auto_white_balance=awb != "off")
    converted = converted.overlay(
        _convert_white_balance_gain_settings(command_settings, default_white_balance_gains)
    )

    return converted


def _convert_image_gain_settings(
    command_settings: dict[str, typing.Any],
) -> hardware.SettingsValues:
    """Convert image gains in MQTT command settings to camera hardware settings.

    Args:
        command_settings: the settings to convert.

    Returns:
        Any image gain-related settings extracted from the MQTT command, but no other settings.

    Raises:
        ValueError: at least one of the MQTT command settings is invalid.
    """
    converted = hardware.SettingsValues()
    # TODO(ethanjli): now that we're using image_gain as the ISO, we should remove one of them
    # from the MQTT API (it could be better to keep ISO since it's tied to metadata, or it could
    # be better to remove ISO since ISO is a fictitious parameter (since the hardware doesn't
    # actually have ISO) and needs a conversion to the real image_gain parameter for the hardware).
    # Then we could delete this function. For now, we'll just redirect both to image_gain, with ISO
    # taking precedence when both are provided in the same command:
    if "image_gain" in command_settings:
        try:
            image_gain = float(command_settings["image_gain"]["analog"])
        except (ValueError, KeyError) as e:
            raise ValueError("Image gain not valid") from e
        converted = converted._replace(image_gain=image_gain)
    if "iso" in command_settings:
        try:
            iso = float(command_settings["iso"])
        except (TypeError, ValueError) as e:
            raise ValueError("Iso number not valid") from e
        converted = converted._replace(image_gain=iso / hardware.ISO_CALIBRATION)

    return converted


def _convert_white_balance_gain_settings(
    command_settings: dict[str, typing.Any],
    # TODO(ethanjli): modify the PlanktoScope GUI to send both red and blue white balance values
    # together each time either is updated, and modify the MQTT API to require both values to be
    # always provided together. That would simplify the code here and remove the need to keep track
    # of previous white balance gains (which could be prone to getting into an inconsistent state
    # compared to the values shown in the GUI); we could maybe even delete this function afterwards.
    default_white_balance_gains: typing.Optional[hardware.WhiteBalanceGains],
) -> hardware.SettingsValues:
    """Convert white-balance gains in MQTT command settings to camera hardware settings.

    Args:
        command_settings: the settings to convert.
        default_white_balance_gains: white-balance gains to substitute for missing values if exactly
          one gain is provided.

    Returns:
        Any white balance gain-related settings extracted from the MQTT command, but no other
        settings.

    Raises:
        ValueError: at least one of the MQTT command settings is invalid.
    """
    converted = hardware.SettingsValues()
    if "white_balance_gain" not in command_settings:
        return converted

    # TODO(ethanjli): change the MQTT API use normal white-balance gains instead of the gains which
    # are multiplied by 100, since the PlanktoScope GUI shows them without the multiplication by 100
    # anyways. That will make the flow of values simpler and easier to follow, since we won't need
    # to transform them on both sides of the API.
    try:
        red_gain = float(command_settings["white_balance_gain"]["red"]) / 100
    except (TypeError, ValueError) as e:
        raise ValueError("White balance gain not valid") from e
    except KeyError as e:
        if default_white_balance_gains is None:
            raise ValueError("White balance gain not valid") from e
        red_gain = default_white_balance_gains.red
    try:
        blue_gain = float(command_settings["white_balance_gain"]["blue"]) / 100
    except (TypeError, ValueError) as e:
        raise ValueError("White balance gain not valid") from e
    except KeyError as e:
        if default_white_balance_gains is None:
            raise ValueError("White balance gain not valid") from e
        blue_gain = default_white_balance_gains.blue
    return converted._replace(
        white_balance_gains=hardware.WhiteBalanceGains(red=red_gain, blue=blue_gain)
    )


# TODO(ethanjli): separate out the status from the error message in the MQTT API, so
# that we can just directly use the error messages from the `hardware.SettingsValues.validate()`
# method, and then we can delete this function. That would be simpler; for now we're trying to keep
# the MQTT API unchanged, so we have this wrapper to return different ValueErrors.
def _validate_settings(settings: hardware.SettingsValues) -> None:
    """Check validity of camera hardware settings.

    Raises:
        ValueError: at least one of the MQTT command settings is invalid.
    """
    if validation_errors := settings.validate():
        loguru.logger.error(
            f"Invalid camera settings requested: {'; '.join(validation_errors)}",
        )
        erroneous_field, _ = validation_errors[0].split(" out of range", 1)
        error_message_mappings = {
            "Exposure time": "Shutter speed",
            "Image gain": "Iso number",
            "Red white-balance gain": "White balance gain",
            "Blue white-balance gain": "White balance gain",
        }
        raise ValueError(
            f"{error_message_mappings.get(erroneous_field, erroneous_field)} not valid",
        )
