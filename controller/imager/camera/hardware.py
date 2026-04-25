"""hardware provides basic I/O abstractions for camera hardware."""

import os
import typing

import libcamera  # type: ignore
import loguru
import picamera2  # type: ignore
from picamera2 import encoders, outputs
from picamera2.platform import Platform, get_platform  # type: ignore
from readerwriterlock import rwlock

# The width & height (in pixels) of camera preview; defaults to the max allowed size for the
# camera sensor:
# capture uses 4056x3040 (4:3 ratio)
preview_size = None
# we use 1440x1080 on RPI4 to stay within the hardware encoder capabilities while maintaining ratio
# anything <= 1920x1080 divisible by 16 (required by H.264 macroblock alignment) (or 2) is fine
# See supported levels with
# v4l2-ctl -D -d /dev/video11 -l -L
# https://en.wikipedia.org/wiki/Advanced_Video_Coding#Levels
if get_platform() == Platform.VC4:
    preview_size = (1440, 1080)
# we use 1920x1440 on RPI5 as it doesn't have hardware encoder and we want to limit bandwidth
# and keep the software encoder resource usage in check
# 1920x1440 maintains the ratio and is macroblock aligned
else:
    preview_size = (1920, 1440)

# This constant is a calibration factor for the Pi HQ camera.
# On the HQ module, “ISO 100” corresponds to an overall gain of ~2.3125 (analogue × digital),
# so we scale gain → ISO-like values with ISO ≈ overall_gain * (100/2.3125).
# This keeps our UI/inputs consistent with the HQ camera’s tuning.
ISO_CALIBRATION = 100 / 2.3125


class StreamConfig(typing.NamedTuple):
    """Values for stream configuration performed exactly once, before the camera starts.

    Fields with `None` values should be ignored as if they were not set.
    """

    # The width & height (in pixels) of captured (non-preview) images; defaults to the max allowed
    # size for the camera sensor:
    capture_size: typing.Optional[tuple[int, int]] = None
    # The width & height (in pixels) of camera preview; defaults to the max allowed size for the
    # camera sensor:
    preview_size: typing.Optional[tuple[int, int]] = preview_size
    # The number of frame buffers to allocate in memory:
    # Note(ethanjli): from testing, it seems that we need at least three buffers to allow the
    # preview to continue receiving frames smoothly from the "lores" stream while a buffer is
    # reserved for saving an image from the "main" stream.
    buffer_count: int = 3
    # Whether to allow the last queued frame to be returned for a capture, even if that frame was
    # saved before the capture request:
    queue: bool = False

    def overlay(self, updates: "StreamConfig") -> "StreamConfig":
        """Create a new instance where provided non-`None` values overwrite existing values."""
        # pylint complains that this namedtuple has no `_asdict()` method even though mypy is fine;
        # this is a false positive:
        # pylint: disable-next=no-member
        return self._replace(
            **{key: value for key, value in updates._asdict().items() if value is not None}
        )


def _picamera2_to_stream_config(config: dict[str, typing.Any]) -> StreamConfig:
    """Create a StreamConfig from a picamera2 pre-start configuration.

    Raises:
        KeyError: the configuration does not contain the required fields.
        ValueError: the configuration does not contain the required fields or values.
    """
    return StreamConfig(
        capture_size=config["main"]["size"],
        preview_size=config["lores"]["size"],
        buffer_count=config["buffer_count"],
        queue=config["queue"],
    )


class WhiteBalanceGains(typing.NamedTuple):
    """Manual white balance gains."""

    red: float
    blue: float


class SettingsValues(typing.NamedTuple):
    """Values for camera settings adjustable anytime after the camera is configured.

    Fields with `None` values should be ignored as if they were not set.
    """

    # picamera2 controls
    auto_exposure: typing.Optional[bool] = None
    exposure_time: typing.Optional[int] = None  # μs; must be within frame_duration_limits
    frame_duration_limits: typing.Optional[tuple[int, int]] = None  # μs
    image_gain: typing.Optional[float] = None  # must be within [0.0, 16.0]
    brightness: typing.Optional[float] = None  # must be within [-1.0, 1.0]
    contrast: typing.Optional[float] = None  # must be within [0.0, 32.0]
    auto_white_balance: typing.Optional[bool] = None
    white_balance_gains: typing.Optional[WhiteBalanceGains] = None  # must be within [0.0, 32.0]
    sharpness: typing.Optional[float] = None  # must be within [0.0, 16.0]

    # picamera2 options
    jpeg_quality: typing.Optional[int] = None  # must be within [0, 95]

    # Note(ethanjli): we can also expose other settings/properties in a similar way, but we don't
    # need them yet and we're trying to minimize the amount of code we have to maintain, so for now
    # I haven't implemented them.

    def validate(self) -> list[str]:
        """Look for values which are invalid because they're out-of-range.

        Returns:
            A list of strings, each representing a validation error.
        """
        value: typing.Any = None
        errors = self._validate_exposure_time()
        if (value := self.image_gain) is not None and not 0.0 <= value <= 16.0:
            errors.append(f"Image gain out of range [0.0, 16.0]: {value}")
        if (value := self.brightness) is not None and not -1.0 <= value <= 1.0:
            errors.append(f"Brightness out of range [-1.0, 1.0]: {value}")
        if (value := self.contrast) is not None and not 0.0 <= value <= 32.0:
            errors.append(f"Contrast out of range [0.0, 32.0]: {value}")
        if (value := self.white_balance_gains) is not None and not 0.0 <= value.red <= 32.0:
            errors.append(f"Red white-balance gain out of range [0.0, 32.0]: {value.red}")
        if (value := self.white_balance_gains) is not None and not 0.0 <= value.blue <= 32.0:
            errors.append(f"Blue white-balance gain out of range [0.0, 32.0]: {value.blue}")
        if (value := self.sharpness) is not None and not 0.0 <= value <= 16.0:
            errors.append(f"Sharpness out of range [0.0, 16.0]: {value}")
        if (value := self.jpeg_quality) is not None and not 0 <= value <= 95:
            errors.append(f"JPEG quality out of range [0, 95]: {value}")

        return errors

    def _validate_exposure_time(self) -> list[str]:
        """Check whether exposure_time is consistent with frame_duration_limits."""
        if (value := self.exposure_time) is None:
            return []

        if (limits := self.frame_duration_limits) is None:
            if value < 0:
                return [f"Exposure time out of range [0, +Inf]: {value}"]
            return []

        # This is a pylint false-positive, since mypy knows `limits` is an unpackable tuple:
        min_limit, max_limit = limits  # pylint: disable=unpacking-non-sequence
        if not min_limit <= value <= max_limit:
            return [f"Exposure time out of range [{min_limit}, {max_limit}]: {value}"]

        return []

    def has_values(self) -> bool:
        """Check whether any values are non-`None`."""
        # pylint complains that this namedtuple has no `_asdict()` method even though mypy is fine;
        # this is a false positive:
        # pylint: disable-next=no-member
        return any(value is not None for value in self._asdict().values())

    def overlay(self, updates: "SettingsValues") -> "SettingsValues":
        """Create a new instance where provided non-`None` values overwrite existing values.

        This is intended to make it easy to combine existing settings with new settings.
        """
        # pylint complains that this namedtuple has no `_asdict()` method even though mypy is fine;
        # this is a false positive:
        # pylint: disable-next=no-member
        return self._replace(
            **{key: value for key, value in updates._asdict().items() if value is not None}
        )

    def as_picamera2_controls(self) -> dict[str, typing.Any]:
        """Create an equivalent dict of values for picamera2's camera controls."""
        result = {
            "AeEnable": self.auto_exposure,
            "ExposureTime": self.exposure_time,
            "AnalogueGain": self.image_gain,
            "Brightness": self.brightness,
            "Contrast": self.contrast,
            "AwbEnable": self.auto_white_balance,
            "ColourGains": self.white_balance_gains,
            "Sharpness": self.sharpness,
        }
        return {key: value for key, value in result.items() if value is not None}

    def as_picamera2_options(self) -> dict[str, typing.Any]:
        """Create an equivalent dict of values suitable for picamera2's camera options."""
        result = {"quality": self.jpeg_quality}
        return {key: value for key, value in result.items() if value is not None}


def _picamera2_to_settings_values(config: dict[str, typing.Any]) -> SettingsValues:
    """Create a SettingsValues from a picamera2 pre-start configuration.

    Raises:
        KeyError: the configuration does not contain the required fields or values.
    """
    frame_duration_limits = config["controls"]["FrameDurationLimits"]
    return SettingsValues(frame_duration_limits=frame_duration_limits)


def config_to_settings_values(config: dict[str, typing.Any]) -> SettingsValues:
    """Create a SettingsValues from a hardware.json configuration."""
    result = SettingsValues()
    # TODO(ethanjli): add exposure time (previously called "shutter speed") and image gain
    # (previously called "iso" but with a different scaling factor) and auto_white_balance to the
    # hardware.json config. Maybe also add jpeg_quality? For details, refer to
    # https://github.com/fairscope/PlanktoScope/issues/290
    if "red_gain" in config or "blue_gain" in config:
        try:
            red_gain = float(config["red_gain"])
            blue_gain = float(config["blue_gain"])
        except KeyError:
            loguru.logger.warning(
                "One of the white balance gains is unspecified! Both gains will be ignored.",
            )
            return result
        except (TypeError, ValueError):
            loguru.logger.warning(
                "White balance gains have incorrect type! Both gains will be ignored.",
            )
            return result
        result = result.overlay(
            SettingsValues(white_balance_gains=WhiteBalanceGains(red=red_gain, blue=blue_gain))
        )
    return result


class PiCamera:
    """A thread-safe and type-safe wrapper around a picamera2-based camera.

    The camera has two streams: a capture stream (for manually triggering image capture) and a
    preview stream (which is continuously updated in the background).
    """

    def __init__(
        self,
        stream_config: StreamConfig = StreamConfig(),
        # Note(ethanjli): mqtt.Worker's constructor explicitly overrides any defaults we set here -
        # to set default initial settings, modify mqtt.Worker's constructor instead!
        initial_settings: SettingsValues = SettingsValues(),
    ) -> None:
        """Set up state needed to initialize the camera, but don't actually start the camera yet.

        Args:
            stream_config: configuration of camera output streams.
            initial_settings: any camera settings to initialize the camera with.
        """
        # Settings & configuration
        self._settings_lock = rwlock.RWLockWrite()
        self._stream_config = stream_config
        self._cached_settings = initial_settings

        self._camera: typing.Optional[picamera2.Picamera2] = None

    def open(self) -> None:
        """Start the camera in the background, including output to the preview stream.

        Blocks until the camera has started.
        """
        loguru.logger.debug("Initializing the camera...")
        try:
            self._camera = picamera2.Picamera2()
        except RuntimeError as e:
            self._camera = None
            raise RuntimeError("Could not initialize the camera!") from e

        loguru.logger.debug(f"Camera sensor_modes: {self._camera.sensor_modes}")

        loguru.logger.debug("Configuring the camera...")
        main_config: dict[str, typing.Any] = {}
        if (main_size := self._stream_config.capture_size) is not None:
            main_config["size"] = main_size
        lores_config: dict[str, typing.Any] = {}
        if (lores_size := self._stream_config.preview_size) is not None:
            lores_config["size"] = lores_size
        # Note(ethanjli): we use the `create_still_configuration` to get the best defaults for still
        # images from the "main" stream:
        # Request BT.601 limited-range YUV (Smpte170m) for the lores stream so that the H.264
        # encoder's default color_range tag (limited) matches the pixel data. Without this, the
        # ISP delivers full-range sYCC YUV but the H.264 VUI advertises limited range, causing
        # browser/RTSP decoders to re-expand the values and display the preview ~5% brighter than
        # the saved JPEG. See docs/preview_luminance_fix/README.md.
        config = self._camera.create_still_configuration(
            main_config,
            lores_config,
            buffer_count=self._stream_config.buffer_count,
            queue=self._stream_config.queue,
            colour_space=libcamera.ColorSpace.Smpte170m(),
        )
        loguru.logger.debug(f"Camera configuration: {config}")
        self._camera.configure(config)
        with self._settings_lock.gen_wlock():
            self._stream_config = self._stream_config.overlay(_picamera2_to_stream_config(config))
            loguru.logger.debug(f"Final stream configuration: {self._stream_config}")

        initial_settings = self._cached_settings.overlay(_picamera2_to_settings_values(config))
        loguru.logger.debug("Initializing camera settings...")
        self.settings = initial_settings

        loguru.logger.debug("Starting the camera...")

        encoder = encoders.H264Encoder(
            # Use baseline profile to optimize for real time / network
            profile="baseline",
            # picamera2-manual.pdf 7.1.1. H264Encoder
            # the bitrate (in bits per second) to use. The default value None will cause the encoder to
            # choose an appropriate bitrate according to the Quality when it starts.
            # bitrate=None,
            # picamera2-manual.pdf 7.1.1. H264Encoder
            # whether to repeat the stream’s sequence headers with every Intra frame (I-frame). This can
            # be sometimes be useful when streaming video over a network, when the client may not receive the start of the
            # stream where the sequence headers would normally be located.
            repeat=True,
            # picamera2-manual.pdf 7.1.1. H264Encoder
            # iperiod (default None) - the number of frames from one I-frame to the next. The value None leaves this at the
            # discretion of the hardware, which defaults to 60 frames.
            iperiod=30,
        )
        encoder.audio = False
        # picamera2-manual.pdf 7.1. Encoders
        # Normally, the encoder of necessity runs at the same frame rate as the camera. By default, every received camera frame
        # gets sent to the encoder. However, you can use the encoder frame_skip_count property to instead receive every nth frame.
        # encoder.frame_skip_count = 2
        # rtsp://$planktoscope:8554/cam/
        output = outputs.PyavOutput("rtsp://127.0.0.1:8554/cam", format="rtsp")
        self._camera.start_recording(
            encoder=encoder,
            output=output,
            # If we specify quality, it overrides the bitrate, contrary to what the picamera2 docs
            # say (refer to
            # https://github.com/raspberrypi/picamera2/blob/63f3be10e317c4b4b0a93e357d7db18fe098e9d4/picamera2/encoders/mjpeg_encoder.py#L23:):
            quality=encoders.Quality.HIGH,
            name="lores",
        )

    @property
    def stream_config(self) -> StreamConfig:
        """An immutable copy of the camera streams configuration."""
        with self._settings_lock.gen_rlock():
            return self._stream_config

    @property
    def settings(self) -> SettingsValues:
        """Adjustable camera settings values."""
        with self._settings_lock.gen_rlock():
            return self._cached_settings

    @settings.setter
    def settings(self, updates: SettingsValues) -> None:
        """Update adjustable camera settings from all provided non-`None` values.

        Fields provided with `None` values are ignored. If any of the provided non-`None` values is
        invalid (e.g. out-of-range), none of the settings will be changed.

        Raises:
            RuntimeError: the method was called before the camera was started, or after it was
              closed.
            ValueError: some of the provided values are out of the allowed ranges.
        """
        if not updates.has_values():
            return
        if self._camera is None:
            raise RuntimeError("The camera has not been started yet!")

        loguru.logger.debug(f"Applying camera settings updates: {updates}")
        with self._settings_lock.gen_wlock():
            new_values = self._cached_settings.overlay(updates)
            loguru.logger.debug(f"New camera settings will be: {new_values}")
            if errors := new_values.validate():
                raise ValueError(f"Invalid settings: {'; '.join(errors)}")
            loguru.logger.debug(f"Setting picamera2 controls: {new_values.as_picamera2_controls()}")
            self._camera.set_controls(new_values.as_picamera2_controls())
            for key, value in updates.as_picamera2_options().items():
                self._camera.options[key] = value
            self._cached_settings = new_values

    def capture_file(self, path: str) -> None:
        """Capture an image from the main stream (in full resolution) and save it as a file.

        Blocks until the image is fully saved.

        Args:
            path: The file path where the image should be saved.

        Raises:
            RuntimeError: the method was called before the camera was started, or after it was
              closed.
        """
        if self._camera is None:
            raise RuntimeError("The camera has not been started yet!")

        loguru.logger.debug(f"Capturing and saving image to {path}...")
        request = self._camera.capture_request()
        # The following lines are false-positives in pylint because they're dynamically-generated
        # members:
        request.save("main", path)  # pylint: disable=no-member
        loguru.logger.debug(
            f"Image metadata: {request.get_metadata()}"  # pylint: disable=no-member
        )

        # Use fsync to ensure write completes
        with open(path, "ab") as f:
            os.fsync(f.fileno())

        request.release()  # pylint: disable=no-member

    def close(self) -> None:
        """Stop and close the camera.

        No more frames will be written to the preview output stream.

        The camera can be restarted after being closed by calling the `start()` method again.
        """
        if self._camera is None:
            return

        loguru.logger.debug("Stopping the camera...")
        # Note(ethanjli): when picamera2 itself crashes while recording in the background, calling
        # `stop_recording()` causes a deadlock! I don't know how to work around that deadlock; this
        # might be an upstream bug which we could fix by upgrading to RPi OS 12, or maybe we need to
        # file an issue with upstream (i.e. in the picamera2 GitHub repo...for now, we'll just try
        # to avoid causing crashes in picamera2 and worry about this problem another day 🤡
        self._camera.stop_recording()

        loguru.logger.debug("Closing the camera...")
        self._camera.close()
        self._camera = None
        self._cached_settings = SettingsValues()
