"""mqtt provides an MQTT worker to perform stop-flow image acquisition."""

import datetime
import json
import os
import sys
import threading
import time
import typing
from concurrent.futures import ProcessPoolExecutor
from uuid import uuid4

import cv2
import loguru
import numpy as np

import integrity
import mqtt
from imager.camera.hardware import ISO_CALIBRATION

from . import stopflow
from .camera import mqtt as camera

# Add segmenter to path so the pool workers can import segment_worker
_segmenter_path = os.path.join(os.path.dirname(__file__), "..", "..", "segmenter")
if _segmenter_path not in sys.path:
    sys.path.insert(0, os.path.abspath(_segmenter_path))


# Flat field configuration
FLATFIELD_PRE_FRAMES = 3  # Number of frames to capture before acquisition for flat field


def calculate_flatfield_reference(frame_paths: list[str]) -> typing.Optional[np.ndarray]:
    """Calculate flat field reference from multiple frames using median.

    Args:
        frame_paths: List of paths to reference frames

    Returns:
        Flat field reference array (float32), or None if calculation failed
    """
    if len(frame_paths) < FLATFIELD_PRE_FRAMES:
        return None

    frames = []
    for path in frame_paths:
        img = cv2.imread(path)
        if img is not None:
            frames.append(img.astype(np.float32))

    if len(frames) < FLATFIELD_PRE_FRAMES:
        return None

    # Stack and compute median
    stacked = np.stack(frames, axis=0)
    flat_ref = np.median(stacked, axis=0)

    # Normalize to mean intensity and clip to avoid division issues
    flat_ref = flat_ref / flat_ref.mean() * 128
    flat_ref = np.clip(flat_ref, 1, 255)

    return flat_ref.astype(np.float32)


class Imager:
    """An MQTT API for the PlanktoScope's camera and image acquisition modules.

    This launches the camera with an MQTT API for settings adjustments
    and launches stop-flow acquisition routines in response to
    commands received over the MQTT API.
    """

    def __init__(self, configuration: dict[str, typing.Any]):
        # Internal state
        self._metadata: dict[str, typing.Any] = {}
        self._active_routine: typing.Optional[ImageAcquisitionRoutine] = None

        # I/O
        self._mqtt: typing.Optional[mqtt.MQTT_Client] = None
        self._pump: typing.Optional[_PumpClient] = None
        self._camera: typing.Optional[camera.Worker] = None

        self.configuration = configuration

        loguru.logger.success("planktoscope.imager is initialized and ready to go!")

    @loguru.logger.catch
    def run(self) -> None:
        loguru.logger.info(f"The imager control thread has been started in process {os.getpid()}")
        self._mqtt = mqtt.MQTT_Client(topic="imager/#", name="imager_client")
        self._mqtt.client.publish("status/imager", '{"status":"Starting up"}')

        loguru.logger.info("Starting the pump RPC client...")
        self._pump = _PumpClient()
        self._pump.open()
        loguru.logger.success("Pump RPC client is ready!")

        loguru.logger.info("Starting the camera...")
        self._camera = camera.Worker(self.configuration)
        self._camera.start()
        if self._camera.camera is None:
            loguru.logger.error("Missing camera - maybe it's disconnected or it never started?")
            self._mqtt.client.publish("status/imager", '{"status": "Error: missing camera"}')
            self._cleanup()
            return

        loguru.logger.success("Camera is ready!")
        self._mqtt.client.publish("status/imager", '{"status":"Ready"}')
        try:
            while True:
                if self._active_routine is not None and not self._active_routine.is_alive():
                    self._active_routine.stop()
                    self._active_routine = None

                if not self._mqtt.new_message_received():
                    time.sleep(0.1)
                    continue
                self._handle_new_message()
        finally:
            loguru.logger.info("Shutting down the imager process...")
            self._mqtt.client.publish("status/imager", '{"status":"Dead"}')
            self._cleanup()
            loguru.logger.success("Imager process shut down!")

    def _cleanup(self) -> None:
        if self._mqtt is not None:
            self._mqtt.shutdown()
            self._mqtt = None
        if self._pump is not None:
            self._pump.close()
            self._pump = None
        if self._camera is not None:
            self._camera.shutdown()
            self._camera.join()
            self._camera = None

    @loguru.logger.catch
    def _handle_new_message(self) -> None:
        assert self._mqtt is not None
        if self._mqtt.msg is None:
            return

        if not self._mqtt.msg["topic"].startswith("imager/"):
            self._mqtt.read_message()
            return

        latest_message = self._mqtt.msg["payload"]
        action = self._mqtt.msg["payload"]["action"]
        self._mqtt.read_message()
        if action == "update_config":
            self._update_metadata(latest_message)
        elif action == "image":
            try:
                self._start_acquisition(latest_message)
            except RuntimeError:
                loguru.logger.exception("Couldn't start image acquisition!")
        elif action == "stop" and self._active_routine is not None:
            self._active_routine.stop()
            self._active_routine = None

    def _update_metadata(self, latest_message: dict[str, typing.Any]) -> None:
        assert self._mqtt is not None
        if self._active_routine is not None and self._active_routine.is_alive():
            loguru.logger.error("Can't update configuration during image acquisition!")
            self._mqtt.client.publish("status/imager", '{"status":"Busy"}')
            return

        if "config" not in latest_message:
            loguru.logger.error(f"Received message is missing field 'config': {latest_message}")
            self._mqtt.client.publish("status/imager", '{"status":"Configuration message error"}')
            return

        loguru.logger.info("Updating configuration...")
        self._metadata = latest_message["config"]
        self._mqtt.client.publish("status/imager", '{"status":"Config updated"}')
        loguru.logger.success("Updated configuration!")

    def _start_acquisition(self, latest_message: dict[str, typing.Any]) -> None:
        assert self._mqtt is not None
        assert self._pump is not None
        assert self._camera is not None

        if (acquisition_settings := _parse_acquisition_settings(latest_message)) is None:
            self._mqtt.client.publish("status/imager", '{"status":"Error"}')
            return
        if self._camera.camera is None:
            loguru.logger.error("Missing camera - maybe it was closed?")
            self._mqtt.client.publish("status/imager", '{"status": "Error: missing camera"}')
            raise RuntimeError("Camera is not available")

        assert (capture_size := self._camera.camera.stream_config.capture_size) is not None
        camera_settings = self._camera.camera.settings
        assert (image_gain := camera_settings.image_gain) is not None
        metadata = {
            **self._metadata,
            "acq_local_datetime": datetime.datetime.now().isoformat().split(".")[0],
            "acq_camera_resolution": f"{capture_size[0]}x{capture_size[1]}",
            "acq_camera_iso": int(image_gain * ISO_CALIBRATION),
            "acq_camera_shutter_speed": camera_settings.exposure_time,
            "acq_uuid": str(uuid4()),
            "sample_uuid": str(uuid4()),
        }
        loguru.logger.debug(f"Saving metadata: {metadata}")
        try:
            output_path = _initialize_acquisition_directory(
                "/home/pi/data/img",
                metadata,
            )
        except ValueError as e:
            self._mqtt.client.publish(
                "status/imager",
                json.dumps({"status": f"Configuration update error: {str(e)}"}),
            )
            return
        if output_path is None:
            return

        live_seg_enabled = bool(latest_message.get("live_segmentation", False))

        self._active_routine = ImageAcquisitionRoutine(
            stopflow.Routine(output_path, acquisition_settings, self._pump, self._camera.camera),
            self._mqtt,
            metadata=metadata,
            live_segmentation=live_seg_enabled,
        )
        self._active_routine.start()


def _parse_acquisition_settings(
    latest_message: dict[str, typing.Any],
) -> typing.Optional[stopflow.Settings]:
    for field in ("nb_frame", "sleep", "volume", "pump_direction"):
        if field not in latest_message:
            loguru.logger.error(
                f"The received message is missing field '{field}': {latest_message}"
            )
            return None

    if latest_message["pump_direction"] not in stopflow.PumpDirection.__members__:
        loguru.logger.error(
            "The received message has an invalid pump direction: "
            + f"{latest_message['pump_direction']}",
        )
        return None

    try:
        return stopflow.Settings(
            total_images=int(latest_message["nb_frame"]),
            stabilization_duration=float(latest_message["sleep"]),
            pump=stopflow.DiscretePumpSettings(
                direction=stopflow.PumpDirection(latest_message.get("pump_direction", "FORWARD")),
                flowrate=float(latest_message.get("pump_flowrate", 2)),
                volume=float(latest_message["volume"]),
            ),
        )
    except ValueError:
        loguru.logger.exception("Invalid input")
        return None


def _initialize_acquisition_directory(
    base_path: str,
    metadata: dict[str, typing.Any],
) -> typing.Optional[str]:
    loguru.logger.info("Setting up the directory structure for storing the pictures...")

    if "object_date" not in metadata:
        loguru.logger.error("The metadata did not contain object_date!")
        raise ValueError("object_date is missing!")

    loguru.logger.debug(f"Metadata: {metadata}")

    acq_dir_path = os.path.join(
        base_path,
        metadata["object_date"],
        str(metadata["sample_id"]).replace(" ", "_").strip("'"),
        str(metadata["acq_id"]).replace(" ", "_").strip("'"),
    )
    if os.path.exists(acq_dir_path):
        loguru.logger.error(f"Acquisition directory {acq_dir_path} already exists!")
        raise ValueError("Chosen id are already in use!")

    os.makedirs(acq_dir_path)
    loguru.logger.info("Saving metadata...")
    metadata_filepath = os.path.join(acq_dir_path, "metadata.json")
    with open(metadata_filepath, "w", encoding="utf-8") as metadata_file:
        json.dump(metadata, metadata_file, indent=4)
        loguru.logger.debug(f"Saved metadata to {metadata_file}: {metadata}")
    integrity.create_integrity_file(acq_dir_path)
    integrity.append_to_integrity_file(metadata_filepath)
    return acq_dir_path


class ImageAcquisitionRoutine(threading.Thread):
    """A thread to run a single image acquisition routine to completion, with MQTT updates."""

    # Number of pool workers for live segmentation (RPi5 has 4 cores, reserve 1 for acquisition)
    POOL_WORKERS = 3

    def __init__(
        self,
        routine: stopflow.Routine,
        mqtt_client: mqtt.MQTT_Client,
        metadata: typing.Optional[dict] = None,
        live_segmentation: bool = False,
    ) -> None:
        super().__init__()
        self._routine = routine
        self._mqtt_client = mqtt_client.client
        self._interrupted = threading.Event()
        self._metadata = metadata or {}
        self._live_segmentation = live_segmentation
        self._pool: typing.Optional[ProcessPoolExecutor] = None
        self._object_id_offset = 0

    def _capture_pre_acquisition_frame(self, index: int) -> typing.Optional[str]:
        """Capture a single pre-acquisition frame for flat field calculation.

        Returns:
            Path to captured frame, or None if interrupted
        """
        if self._interrupted.is_set():
            return None

        # Pump sample
        self._routine._pump.run_discrete(self._routine.settings.pump)

        if self._interrupted.is_set():
            return None

        # Wait for stabilization
        time.sleep(self._routine.settings.stabilization_duration)

        if self._interrupted.is_set():
            return None

        # Capture frame
        filename = f".flatfield_pre_{index}.jpg"
        capture_path = os.path.join(self._routine.output_path, filename)
        self._routine._camera.capture_file(capture_path)

        return capture_path

    def _calculate_pre_acquisition_flatfield(self) -> bool:
        """Capture pre-acquisition frames and calculate flat field.

        Returns:
            True if flat field was calculated successfully, False otherwise
        """
        loguru.logger.info("Starting pre-acquisition flat field calculation...")
        self._mqtt_client.publish(
            "status/imager",
            json.dumps({"status": "Calculating flat field...", "step": 0, "total": FLATFIELD_PRE_FRAMES})
        )

        pre_frame_paths = []

        for i in range(FLATFIELD_PRE_FRAMES):
            if self._interrupted.is_set():
                loguru.logger.info("Pre-acquisition flat field calculation interrupted")
                return False

            self._mqtt_client.publish(
                "status/imager",
                json.dumps({
                    "status": "Calculating flat field...",
                    "step": i + 1,
                    "total": FLATFIELD_PRE_FRAMES
                })
            )

            loguru.logger.info(f"Capturing pre-acquisition frame {i + 1}/{FLATFIELD_PRE_FRAMES}")

            path = self._capture_pre_acquisition_frame(i)
            if path is None:
                return False
            pre_frame_paths.append(path)

        # Calculate flat field from captured frames
        loguru.logger.info("Computing flat field reference from pre-acquisition frames...")
        flat_ref = calculate_flatfield_reference(pre_frame_paths)

        if flat_ref is not None:
            # Save flat field reference
            flat_path = os.path.join(self._routine.output_path, ".flatfield_ref.npy")
            np.save(flat_path, flat_ref)
            loguru.logger.success(f"Flat field reference saved to {flat_path}")

            self._mqtt_client.publish(
                "status/imager",
                json.dumps({"status": "Flat field ready"})
            )
            return True
        else:
            loguru.logger.warning("Failed to calculate flat field reference")
            return False

    def _setup_live_segmentation(self) -> None:
        """Set up ProcessPoolExecutor and wire the segmentation callback into the routine."""
        if not self._live_segmentation:
            return

        loguru.logger.info(f"Starting live segmentation pool with {self.POOL_WORKERS} workers")
        self._pool = ProcessPoolExecutor(max_workers=self.POOL_WORKERS)

        # Determine flat field reference path (from pre-acquisition phase)
        flat_ref_path = os.path.join(self._routine.output_path, ".flatfield_ref.npy")
        if not os.path.exists(flat_ref_path):
            flat_ref_path = None

        # Build the objects output directory (mirrors img path structure under /home/pi/data/objects/)
        img_base = "/home/pi/data/img"
        objects_base = "/home/pi/data/objects"
        if self._routine.output_path.startswith(img_base):
            rel_path = os.path.relpath(self._routine.output_path, img_base)
            objects_dir = os.path.join(objects_base, rel_path)
        else:
            objects_dir = os.path.join(self._routine.output_path, "objects")

        min_esd = float(self._metadata.get("process_min_esd", 20.0))
        # Pre-allocate 10000 object IDs per frame to avoid collisions between
        # concurrent workers. Frame 0 gets IDs 0-9999, frame 1 gets 10000-19999, etc.
        objects_per_frame_block = 10000

        def submit_frame(image_path: str, frame_index: int):
            from segment_worker import segment_frame
            return self._pool.submit(
                segment_frame,
                image_path=image_path,
                objects_dir=objects_dir,
                flat_ref_path=flat_ref_path,
                metadata=self._metadata,
                frame_index=frame_index,
                object_id_offset=frame_index * objects_per_frame_block,
                min_esd_um=min_esd,
            )

        self._routine._on_frame_captured = submit_frame

    def _teardown_live_segmentation(self, interrupted: bool = False) -> None:
        """Drain or cancel pending segmentation and shut down the pool."""
        if self._pool is None:
            return

        if interrupted:
            loguru.logger.info("Cancelling pending live segmentation tasks...")
            self._routine.cancel_segmentation()
        else:
            loguru.logger.info("Draining remaining live segmentation tasks...")
            self._mqtt_client.publish(
                "status/imager",
                '{"status":"Finishing segmentation..."}',
            )
            results = self._routine.drain_segmentation(timeout=120.0)
            total_objects = sum(r.get("objects_saved", 0) for r in results)
            errors = [r for r in results if r.get("error")]
            loguru.logger.info(
                f"Live segmentation complete: {total_objects} objects from "
                f"{len(results)} frames, {len(errors)} errors"
            )

        self._pool.shutdown(wait=not interrupted, cancel_futures=interrupted)
        self._pool = None

    def run(self) -> None:
        """Run a stop-flow image-acquisition routine until completion or interruption."""

        # Phase 1: Pre-acquisition flat field calculation
        if not self._calculate_pre_acquisition_flatfield():
            if self._interrupted.is_set():
                self._mqtt_client.publish("status/imager", '{"status":"Interrupted"}')
                return
            # Continue anyway even if flat field calculation failed
            loguru.logger.warning("Continuing without pre-acquisition flat field")

        # Phase 2: Set up live segmentation pool (if enabled)
        self._setup_live_segmentation()

        # Phase 3: Main acquisition loop
        self._mqtt_client.publish("status/imager", '{"status":"Started"}')
        was_interrupted = False

        try:
            while True:
                if (result := self._routine.run_step()) is None:
                    if self._routine.interrupted or self._interrupted.is_set():
                        loguru.logger.debug("Image-acquisition routine was interrupted!")
                        self._mqtt_client.publish("status/imager", '{"status":"Interrupted"}')
                        was_interrupted = True
                        break
                    loguru.logger.debug("Image-acquisition routine ran to completion!")
                    break

                index, filename = result
                path = os.path.join(self._routine.output_path, filename)
                try:
                    integrity.append_to_integrity_file(path)
                except FileNotFoundError:
                    self._mqtt_client.publish(
                        "status/imager",
                        f'{{"status":"Image {index + 1}/{self._routine.settings.total_images} '
                        + 'WAS NOT CAPTURED! STOPPING THE PROCESS!"}}',
                    )
                    break

                self._mqtt_client.publish(
                    "status/imager",
                    f'{{"status":"Image {index + 1}/{self._routine.settings.total_images} '
                    + f'saved to {filename}"}}',
                )
                self._mqtt_client.publish(
                    "status/imager",
                    json.dumps(
                        {
                            "type": "progress",
                            "path": path,
                            "current": index + 1,
                            "total": self._routine.settings.total_images,
                        }
                    ),
                )
        finally:
            # Phase 4: Drain or cancel live segmentation
            self._teardown_live_segmentation(interrupted=was_interrupted)

        if not was_interrupted:
            self._mqtt_client.publish(
                "status/imager",
                json.dumps(
                    {
                        "status": "Done",
                        "path": self._routine.output_path,
                    }
                ),
            )

    def stop(self) -> None:
        """Stop the thread."""
        self._interrupted.set()
        self._routine.stop()
        self.join()


class _PumpClient:
    """Thread-safe RPC stub for remotely controlling the pump over MQTT."""

    def __init__(self) -> None:
        self._mqtt: typing.Optional[mqtt.MQTT_Client] = None
        self._mqtt_receiver_thread: typing.Optional[threading.Thread] = None
        self._stop_receiving_mqtt = threading.Event()
        self._done = threading.Event()
        self._discrete_run = threading.Lock()

    def open(self) -> None:
        if self._mqtt is not None:
            return

        self._mqtt = mqtt.MQTT_Client(topic="status/pump", name="imager_pump_client")
        self._mqtt_receiver_thread = threading.Thread(target=self._receive_messages)
        self._mqtt_receiver_thread.start()

    def _receive_messages(self) -> None:
        assert self._mqtt is not None

        while not self._stop_receiving_mqtt.is_set():
            if not self._mqtt.new_message_received():
                time.sleep(0.1)
                continue
            if self._mqtt.msg is None or self._mqtt.msg["topic"] != "status/pump":
                continue

            if self._mqtt.msg["payload"]["status"] not in {"Done", "Interrupted"}:
                loguru.logger.debug(f"Ignoring pump status update: {self._mqtt.msg['payload']}")
                self._mqtt.read_message()
                continue

            loguru.logger.debug(f"The pump has stopped: {self._mqtt.msg['payload']}")
            self._mqtt.read_message()
            self._done.set()
            if self._discrete_run.locked():
                self._discrete_run.release()

    def run_discrete(self, settings: stopflow.DiscretePumpSettings) -> None:
        if self._mqtt is None:
            raise RuntimeError("MQTT client was not initialized yet!")

        self._discrete_run.acquire()
        self._done.clear()
        self._mqtt.client.publish(
            "actuator/pump",
            json.dumps(
                {
                    "action": "move",
                    "direction": settings.direction.value,
                    "flowrate": settings.flowrate,
                    "volume": settings.volume,
                }
            ),
        )
        self._done.wait()

    def stop(self) -> None:
        if self._mqtt is None:
            raise RuntimeError("MQTT client was not initialized yet!")

        self._mqtt.client.publish("actuator/pump", '{"action": "stop"}')

    def close(self) -> None:
        if self._mqtt is None:
            return

        self._stop_receiving_mqtt.set()
        if self._mqtt_receiver_thread is not None:
            self._mqtt_receiver_thread.join()
        self._mqtt_receiver_thread = None
        self._mqtt.shutdown()
        self._mqtt = None

        if not self._discrete_run.locked():
            return
        self._discrete_run.release()


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
    configuration = read_config()
    imager = Imager(configuration)
    imager.run()


if __name__ == "__main__":
    main()
