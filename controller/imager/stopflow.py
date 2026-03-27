"""stopflow provides the domain logic for stop-flow imaging.

No actual I/O (hardware control, filesystem interaction, or MQTT messaging) should be added to this
module; instead, I/O drivers should be defined elsewhere and passed into functions/methods in this
module. This will allow us to write automated tests for the domain logic for stop-flow imaging
which we can run without a PlanktoScope.
"""

import datetime as dt
import enum
import os
import threading
import typing
from concurrent.futures import Future

import loguru
import typing_extensions


# TODO(ethanjli): move this to the pump module and rename it to `Direction`
# TODO(ethanjli): when we upgrade to python3.11+, just use a [enum.StrEnum]
class PumpDirection(enum.Enum):
    """The allowed pump directions."""

    FORWARD = "FORWARD"
    BACKWARD = "BACKWARD"


class DiscretePumpSettings(typing.NamedTuple):
    """Settings for pumping a discrete volume of sample."""

    # TODO(ethanjli): move this to the pump module and rename it to `Settings`
    direction: PumpDirection
    flowrate: float  # mL/min
    volume: float  # mL


class PumpRunner(typing_extensions.Protocol):
    """Interface for an interruptible pump which can pump a discrete volume."""

    def stop(self) -> None:
        """Stop the pump."""

    def run_discrete(self, settings: DiscretePumpSettings) -> None:
        """Run the pump for a discrete volume at the specified flow rate and direction.

        Blocks until the pump has finished pumping, or until the `stop()` method is called.
        """


class FileCapturer(typing_extensions.Protocol):
    """Interface for something which can capture images to files."""

    def capture_file(self, filename: str) -> None:
        """Capture an image to the specified filename."""


class Settings(typing.NamedTuple):
    """Settings for the stop-flow routine."""

    total_images: int
    stabilization_duration: float  # sec
    pump: DiscretePumpSettings


class SegmentationCallback(typing_extensions.Protocol):
    """Interface for submitting a frame to live segmentation."""

    def __call__(self, image_path: str, frame_index: int) -> typing.Optional[Future]:
        """Submit a frame for segmentation.

        Args:
            image_path: path to the captured frame.
            frame_index: 0-based index of this frame.

        Returns:
            A Future representing the pending segmentation, or None if segmentation is disabled.
        """


class Routine:
    """A thread-safe stop-flow image acquisition routine.

    This class tracks the internal state of the routine. A new object should be instantiated from
    this class every time a new image-acquisition routine is started, to reset all internal state.

    Attribs:
        output_path: the directory where images are saved by the routine.
        settings: the image-acquisition settings.
    """

    def __init__(
        self,
        output_path: str,
        settings: Settings,
        pump: PumpRunner,
        camera: FileCapturer,
        on_frame_captured: typing.Optional[SegmentationCallback] = None,
    ) -> None:
        """Initialize the image-acquisition routine.

        Args:
            output_path: the directory to save acquired images and metadata files. This is assumed
              not to exist.
            settings: stop-flow routine settings.
            pump: the sample pump.
            camera: the camera.
            on_frame_captured: optional callback to submit each frame for live segmentation.
        """
        # Parameters
        self.output_path: typing.Final[str] = output_path
        self.settings: typing.Final[Settings] = settings

        # I/O (actuators)
        self._pump = pump
        self._camera = camera

        # Live segmentation callback
        self._on_frame_captured = on_frame_captured

        # Routine state
        self._interrupted = threading.Event()  # routine interrupted before completion
        self._progress = 0  # the number of images acquired so far
        self._progress_lock = threading.Lock()
        self._seg_futures: list[Future] = []  # pending segmentation futures

    def run_step(self) -> typing.Optional[tuple[int, str]]:
        """Run a single step of the stop-flow imaging routine.

        Does nothing if the routine is already done (whether because all images have already been
        acquired, or because the routine was manually interrupted by calling the `stop()` method).
        Blocks until the step is complete (whether because it has finished or because the routine
        was manually interrupted).

        Returns:
            The index of the image which was just saved and the filename of the image which was just
            saved, or `None` if the routine was already done
        """
        if self.interrupted:
            return None
        with self._progress_lock:
            if self._progress >= self.settings.total_images:
                return None

        self._pump.run_discrete(self.settings.pump)
        if self._interrupted.wait(timeout=self.settings.stabilization_duration):
            loguru.logger.info("Image acquisition was interrupted during an acquisition step!")
            return None

        with self._progress_lock:
            filename = f"{dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d_%H-%M-%S-%f')}.jpg"
            capture_path = os.path.join(self.output_path, filename)
            loguru.logger.info(
                f"Capturing image {self._progress + 1}/{self.settings.total_images} to "
                + f"{capture_path}...",
            )
            self._camera.capture_file(capture_path)

            # Submit frame to live segmentation pool (non-blocking)
            if self._on_frame_captured is not None:
                try:
                    future = self._on_frame_captured(capture_path, self._progress)
                    if future is not None:
                        self._seg_futures.append(future)
                except Exception as e:
                    loguru.logger.warning(f"Live segmentation submit failed: {e}")

            # Note(ethanjli): updating the integrity file is the responsibility of the code which
            # calls this `run_step()` method.

            acquired_index = self._progress
            self._progress += 1
            return acquired_index, filename

    def stop(self) -> None:
        """Stop the routine if it's running."""
        with self._progress_lock:
            if self._progress >= self.settings.total_images:
                return

            self._interrupted.set()
            self._pump.stop()
            loguru.logger.info("The image-acquisition routine has been interrupted!")

    def drain_segmentation(self, timeout: float = 120.0) -> list[dict]:
        """Wait for all pending segmentation futures to complete.

        Args:
            timeout: maximum seconds to wait for all futures.

        Returns:
            List of result dicts from completed segmentation workers.
        """
        results = []
        for future in self._seg_futures:
            try:
                result = future.result(timeout=timeout)
                results.append(result)
            except Exception as e:
                loguru.logger.warning(f"Segmentation future failed: {e}")
                results.append({"error": str(e)})
        self._seg_futures.clear()
        return results

    def cancel_segmentation(self) -> None:
        """Cancel all pending segmentation futures."""
        for future in self._seg_futures:
            future.cancel()
        self._seg_futures.clear()

    @property
    def interrupted(self) -> bool:
        """Check whether the routine was manually interrupted."""
        return self._interrupted.is_set()
