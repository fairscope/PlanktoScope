"""mqtt provides an MQTT worker to perform stop-flow image acquisition."""

import datetime
import json
import os
import threading
import time
import typing
from uuid import uuid4

import loguru

import integrity
import mqtt
from imager.camera.hardware import ISO_CALIBRATION

from . import stopflow
from .camera import mqtt as camera


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
        # TODO(ethanjli): instead of having the ImagerWorker start the camera worker, this should
        # be started from the main script; and then the camera object should be passed into the
        # constructor.
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
            # TODO(ethanjli): officially add this error status to the MQTT API!
            self._mqtt.client.publish("status/imager", '{"status": "Error: missing camera"}')
            self._cleanup()
            return

        loguru.logger.success("Camera is ready!")
        self._mqtt.client.publish("status/imager", '{"status":"Ready"}')
        try:
            while True:
                if self._active_routine is not None and not self._active_routine.is_alive():
                    # Garbage-collect any finished image-acquisition routine threads so that we're
                    # ready for the next configuration update command which arrives:
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
        """Clean up everything running in the background."""
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
        """Handle a new message received over MQTT."""
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
        """Handle a new imager command to update the configuration (i.e. the metadata)."""
        assert self._mqtt is not None

        # TODO(ethanjli): it'll be simpler if we just take the configuration as part of the command
        # to start image acquisition! This requires modifying the MQTT API (to remove the
        # "update_config" action and require the client to pass the metadata with the "image"
        # action), so we'll do it later.
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
        """Handle a new imager command to start image acquisition."""
        assert self._mqtt is not None
        assert self._pump is not None
        assert self._camera is not None

        if (acquisition_settings := _parse_acquisition_settings(latest_message)) is None:
            self._mqtt.client.publish("status/imager", '{"status":"Error"}')
            return
        if self._camera.camera is None:
            loguru.logger.error("Missing camera - maybe it was closed?")
            # TODO(ethanjli): officially add this error status to the MQTT API!
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
            # An error status was already reported, so we don't need to do anything else
            return

        self._active_routine = ImageAcquisitionRoutine(
            stopflow.Routine(output_path, acquisition_settings, self._pump, self._camera.camera),
            self._mqtt,
        )
        self._active_routine.start()


def _parse_acquisition_settings(
    latest_message: dict[str, typing.Any],
) -> typing.Optional[stopflow.Settings]:
    """Parse a command to start acquisition into stop-flow settings.

    Returns:
        A [stopflow.Settings] with the parsed settings if input validation and parsing succeeded,
        or `None` otherwise.
    """
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
    """Make the directory where images will be saved for the current image-acquisition routine.

    This also saves the metadata to a `metadata.json` file and initializes a file integrity log in
    the directory.

    Args:
        base_path: directory under which a subdirectory tree will be created for the image
          acquisition.
        metadata: a dict of all metadata to be associated with the acquisition. Must contain
          keys "object_date", "sample_id", and "acq_id".

    Returns:
        The directory where captured images will be saved if preparation finished successfully,
        or `None` otherwise.

    Raises:
        ValueError: Acquisition directory initialization failed.
    """
    loguru.logger.info("Setting up the directory structure for storing the pictures...")

    if "object_date" not in metadata:  # needed for the directory path
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

    # TODO(ethanjli): instead of taking an arg of type mqtt.MQTT_CLIENT, just take an arg of
    # whatever `mqtt_client.client`'s type is supposed to be. Or maybe we should just initialize
    # our own MQTT client in here?
    def __init__(self, routine: stopflow.Routine, mqtt_client: mqtt.MQTT_Client) -> None:
        """Initialize the thread.

        Args:
            routine: the image-acquisition routine to run.
            mqtt_client: an MQTT client which will be used to broadcast updates.
        """
        super().__init__()
        self._routine = routine
        self._mqtt_client = mqtt_client.client

    def run(self) -> None:
        """Run a stop-flow image-acquisition routine until completion or interruption."""
        self._mqtt_client.publish("status/imager", '{"status":"Started"}')
        while True:
            if (result := self._routine.run_step()) is None:
                if self._routine.interrupted:
                    loguru.logger.debug("Image-acquisition routine was interrupted!")
                    self._mqtt_client.publish("status/imager", '{"status":"Interrupted"}')
                    break
                loguru.logger.debug("Image-acquisition routine ran to completion!")
                self._mqtt_client.publish(
                    "status/imager",
                    json.dumps(
                        {
                            "status": "Done",
                            "path": self._routine.output_path,
                        }
                    ),
                )
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

            # FIXME: remove
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

    def stop(self) -> None:
        """Stop the thread.

        Blocks until the thread is done.

        Raises:
            RuntimeError: this method was called before the thread was started.
        """
        self._routine.stop()
        self.join()


# TODO(ethanjli): rearchitect the hardware controller so that the imager can directly call pump
# methods (by running all modules in the same process), so that we can just delete this entire class
# and simplify function calls between the imager and the pump! This will require launching the
# pump and the imager as threads in the same process, rather than launching them as separate
# processes.
class _PumpClient:
    """Thread-safe RPC stub for remotely controlling the pump over MQTT."""

    def __init__(self) -> None:
        """Initialize the stub."""
        # Note(ethanjli): We have to have our own MQTT client because we need to publish messages
        # from a separate thread, and currently the MQTT client isn't thread-safe (it deadlocks
        # if we don't have a separate MQTT client):
        self._mqtt: typing.Optional[mqtt.MQTT_Client] = None
        self._mqtt_receiver_thread: typing.Optional[threading.Thread] = None
        self._stop_receiving_mqtt = threading.Event()  # close() was called
        self._done = threading.Event()  # run_discrete() finished or stop() was called
        self._discrete_run = threading.Lock()  # mutex on starting the pump

    def open(self) -> None:
        """Start the pump MQTT client.

        Launches a thread to listen for MQTT updates from the pump. After this method is called,
        the `run_discrete()` and `stop()` methods can be called.
        """
        if self._mqtt is not None:
            return

        self._mqtt = mqtt.MQTT_Client(topic="status/pump", name="imager_pump_client")
        self._mqtt_receiver_thread = threading.Thread(target=self._receive_messages)
        self._mqtt_receiver_thread.start()

    def _receive_messages(self) -> None:
        """Update internal state based on pump status updates received over MQTT."""
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
        """Run the pump for a discrete volume at the specified flow rate and direction.

        Blocks until the pump has finished pumping. Before starting the pump, this first blocks
        until the previous `run_discrete()` call (if it was started in another thread and is still
        running) has finished.

        Raises:
            RuntimeError: this method was called before the `open()` method was called, or after
              the `close()` method was called.
        """
        if self._mqtt is None:
            raise RuntimeError("MQTT client was not initialized yet!")

        # We ignore the pylint error here because the lock can only be released from a different
        # thread (the thread which calls the `handle_status_update()` method):
        self._discrete_run.acquire()  # pylint: disable=consider-using-with
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
        """Stop the pump."""
        if self._mqtt is None:
            raise RuntimeError("MQTT client was not initialized yet!")

        self._mqtt.client.publish("actuator/pump", '{"action": "stop"}')

    def close(self) -> None:
        """Close the pump MQTT client, if it's currently open.

        Stops the MQTT receiver thread and blocks until it finishes. After this method is called,
        no methods are allowed to be called.
        """
        if self._mqtt is None:
            return

        self._stop_receiving_mqtt.set()
        if self._mqtt_receiver_thread is not None:
            self._mqtt_receiver_thread.join()
        self._mqtt_receiver_thread = None
        self._mqtt.shutdown()
        self._mqtt = None

        # We don't know if the run is done (or if it'll ever finish), but we'll release the lock to
        # prevent deadlocks:
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
