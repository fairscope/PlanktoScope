# Copyright (C) 2021 Romain Bazile
#
# This file is part of the PlanktoScope software.
#
# PlanktoScope is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# PlanktoScope is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with PlanktoScope.  If not, see <http://www.gnu.org/licenses/>.

"""Live segmentation module for acquisition overlay analysis.

This module provides real-time segmentation during acquisition. When enabled,
it listens for image captures from the imager and segments each frame as it
is captured, publishing results for overlay display.

Features:
- Real-time segmentation overlay for preview
- Saves object crops to /home/pi/data/objects for visualization
- Writes EcoTaxa-compatible TSV incrementally
- Publishes MQTT updates for live dashboard refresh
"""

import base64
import io
import json
import math
import multiprocessing
import os
import time
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
import PIL.Image
import skimage.measure
from loguru import logger

import planktoscope.mqtt
import planktoscope.segmenter.operations
import planktoscope.segmenter.encoder

logger.info("planktoscope.segmenter.live is loaded")

# Hardware config path (same as used by controller)
HARDWARE_CONFIG_PATH = "/home/pi/PlanktoScope/hardware.json"

# Paths for visualization output
IMG_BASE = "/home/pi/data/img"
OBJECTS_BASE = "/home/pi/data/objects"
LIVE_STATS_FILE = "/tmp/live_seg_stats.json"

# EcoTaxa TSV column headers
ECOTAXA_COLUMNS = [
    "object_id", "object_date", "object_time",
    "object_x", "object_y", "object_width", "object_height",
    "object_area", "object_perim.", "object_major", "object_minor",
    "object_circ.", "object_elongation", "object_solidity",
    "object_equivalent_diameter",
    "object_MeanHue", "object_MeanSaturation", "object_MeanValue",
    "object_blur_laplacian",
    "sample_id", "acq_id", "img_file_name"
]


class LiveSegmenterProcess(multiprocessing.Process):
    """Live segmentation worker that analyzes frames during acquisition.

    This process listens for image captures from the imager during acquisition
    and performs real-time segmentation on each captured frame. Results are
    published via MQTT for overlay display on the frontend.
    """

    @logger.catch
    def __init__(self, event, data_path):
        """Initialize the LiveSegmenter class.

        Args:
            event (multiprocessing.Event): shutdown event
            data_path (str): base data path
        """
        super(LiveSegmenterProcess, self).__init__(name="live_segmenter")

        logger.info("planktoscope.segmenter.live is initialising")

        self.stop_event = event
        self.live_client = None
        self.imager_client = None
        self.__data_path = data_path
        self.__enabled = False  # Whether live segmentation overlay is enabled
        self.__overlay_mode = "bbox"  # bbox, mask, or both
        self.__min_area = 100  # Minimum area in pixels for detected objects
        self.__pixel_size_um = self._load_pixel_size()  # Load from hardware config
        self.__remove_static = False  # Remove objects that appear in same position across frames
        self.__static_tracker = {}  # Track objects by position: {(cx, cy): frame_count}
        self.__static_threshold = 2  # FIX: Reduced from 3 to 2 for faster debris detection

        # Visualization state
        self.__save_crops = True  # Save object crops for visualization gallery
        self.__current_acq_folder = None
        self.__object_counter = 0
        self.__frame_counter = 0

        logger.success("planktoscope.segmenter.live is initialised and ready to go!")

    def _load_pixel_size(self):
        """Load pixel size from hardware config file.

        Reads process_pixel_fixed from /home/pi/PlanktoScope/hardware.json.
        This ensures consistency with the calibration value set in the dashboard.

        Returns:
            float: Pixel size in micrometers per pixel. Defaults to 0.75 if not found.
        """
        default_pixel_size = 0.75
        try:
            with open(HARDWARE_CONFIG_PATH, "r") as f:
                config = json.load(f)
                pixel_size = config.get("process_pixel_fixed", default_pixel_size)
                logger.info(f"Loaded pixel size from hardware config: {pixel_size} µm/pixel")
                return float(pixel_size)
        except FileNotFoundError:
            logger.warning(
                f"Hardware config not found at {HARDWARE_CONFIG_PATH}, "
                f"using default pixel size: {default_pixel_size} µm/pixel"
            )
            return default_pixel_size
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(
                f"Error reading hardware config: {e}, "
                f"using default pixel size: {default_pixel_size} µm/pixel"
            )
            return default_pixel_size

    def _get_acquisition_info(self, image_path):
        """Extract acquisition info from image path.

        Path format: /home/pi/data/img/DATE/SAMPLE_ID/ACQ_ID/image.jpg
        """
        try:
            parts = image_path.split("/")
            if "img" in parts:
                idx = parts.index("img")
                date_folder = parts[idx + 1] if len(parts) > idx + 1 else ""
                sample_folder = parts[idx + 2] if len(parts) > idx + 2 else ""
                acq_folder = parts[idx + 3] if len(parts) > idx + 3 else ""

                return {
                    "date": date_folder,
                    "sample_id": sample_folder,
                    "acq_id": acq_folder,
                    "acq_folder": acq_folder,
                }
        except Exception:
            pass

        return {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "sample_id": "unknown",
            "acq_id": "A_0",
            "acq_folder": "unknown",
        }

    def _derive_output_dir(self, image_path):
        """Get output directory for object crops, mirroring img structure."""
        abs_path = os.path.abspath(image_path)
        img_dir = os.path.dirname(abs_path)

        if img_dir.startswith(IMG_BASE):
            rel_path = os.path.relpath(img_dir, IMG_BASE)
            return os.path.join(OBJECTS_BASE, rel_path)
        return os.path.join(img_dir, "objects")

    def _write_tsv_header(self, tsv_path):
        """Write EcoTaxa TSV header."""
        try:
            with open(tsv_path, "w") as f:
                f.write("\t".join(ECOTAXA_COLUMNS) + "\n")
                types = ["[t]"] * len(ECOTAXA_COLUMNS)
                f.write("\t".join(types) + "\n")
            return True
        except Exception as e:
            logger.error(f"Failed to write TSV header: {e}")
            return False

    def _append_tsv_row(self, tsv_path, row_data):
        """Append a single row to the TSV file."""
        try:
            with open(tsv_path, "a") as f:
                values = []
                for col in ECOTAXA_COLUMNS:
                    val = row_data.get(col, "")
                    if isinstance(val, float):
                        values.append(f"{val:.4f}")
                    else:
                        values.append(str(val))
                f.write("\t".join(values) + "\n")
            return True
        except Exception as e:
            logger.error(f"Failed to append TSV row: {e}")
            return False

    def _extract_object_features(self, img, region, bbox):
        """Extract morphological features from an object for TSV."""
        x, y, w, h = bbox

        # Extract ROI
        roi_img = img[y:y+h, x:x+w]

        # Area and perimeter from region
        area = int(region.area)
        perimeter = float(region.perimeter)

        # Major/minor axes
        major = float(region.major_axis_length) if region.major_axis_length else max(w, h)
        minor = float(region.minor_axis_length) if region.minor_axis_length else min(w, h)

        # Derived metrics
        circularity = (4 * math.pi * area / (perimeter ** 2)) if perimeter > 0 else 0
        elongation = major / minor if minor > 0 else 1.0
        solidity = float(region.solidity) if region.solidity else 1.0
        equivalent_diameter = float(region.equivalent_diameter) if region.equivalent_diameter else (4 * area / math.pi) ** 0.5

        # HSV color statistics
        mean_hue, mean_sat, mean_val = 0, 0, 0
        try:
            roi_hsv = cv2.cvtColor(roi_img, cv2.COLOR_BGR2HSV)
            mean_hue = float(np.mean(roi_hsv[:, :, 0]))
            mean_sat = float(np.mean(roi_hsv[:, :, 1]))
            mean_val = float(np.mean(roi_hsv[:, :, 2]))
        except Exception:
            pass

        # Blur metric
        blur_laplacian = planktoscope.segmenter.operations.calculate_blur(roi_img)

        return {
            "object_x": x + w / 2,
            "object_y": y + h / 2,
            "object_width": w,
            "object_height": h,
            "object_area": area,
            "object_perim.": perimeter,
            "object_major": major,
            "object_minor": minor,
            "object_circ.": circularity,
            "object_elongation": elongation,
            "object_solidity": solidity,
            "object_equivalent_diameter": equivalent_diameter,
            "object_MeanHue": mean_hue,
            "object_MeanSaturation": mean_sat,
            "object_MeanValue": mean_val,
            "object_blur_laplacian": blur_laplacian,
        }

    def _publish_visualization_update(self, output_dir, total_objects, total_frames):
        """Publish MQTT update for visualization dashboard refresh."""
        try:
            message = {
                "status": "segmenting",
                "total_objects": total_objects,
                "total_images": total_frames,
                "output_dir": output_dir,
                "timestamp": time.time(),
            }
            self.live_client.client.publish(
                "status/segmentation",
                json.dumps(message),
            )
        except Exception as e:
            logger.debug(f"Failed to publish visualization update: {e}")

    def _esd_um_to_min_area(self, esd_um):
        """Convert ESD in micrometers to minimum area in pixels.

        Args:
            esd_um (float): Equivalent spherical diameter in micrometers

        Returns:
            int: Minimum area in pixels
        """
        # Convert ESD from micrometers to pixels
        esd_pixels = esd_um / self.__pixel_size_um
        # Calculate area of a circle with this diameter
        area = math.pi * (esd_pixels / 2) ** 2
        return int(area)

    def _create_simple_mask(self, img):
        """Create a mask using simple thresholding.

        Args:
            img (np.array): BGR image

        Returns:
            np.array: binary mask
        """
        mask = planktoscope.segmenter.operations.simple_threshold(img)
        mask = planktoscope.segmenter.operations.erode(mask)
        mask = planktoscope.segmenter.operations.dilate(mask)
        return mask

    def _get_bbox_key(self, bbox):
        """Get a grid key for a bounding box center for tracking.

        Uses 100px grid cells - large enough to tolerate detection variation
        in elongated objects while still distinguishing separate small objects.

        Args:
            bbox: [x, y, w, h] bounding box

        Returns:
            tuple: (grid_x, grid_y) key
        """
        cx = bbox[0] + bbox[2] / 2
        cy = bbox[1] + bbox[3] / 2
        grid_size = 100  # FIX: Larger grid (was 60) tolerates detection jitter for stuck objects
        return (int(cx / grid_size), int(cy / grid_size))

    def _update_static_tracker(self, current_bboxes):
        """Update the static object tracker with current frame's objects.

        Objects that appear in the same grid cell across multiple frames
        get their count incremented. Objects not seen are removed.

        Args:
            current_bboxes: list of [x, y, w, h] bounding boxes from current frame
        """
        # Get all current grid positions
        current_keys = set()
        for bbox in current_bboxes:
            key = self._get_bbox_key(bbox)
            current_keys.add(key)

        # Update tracker: increment seen, remove unseen
        new_tracker = {}
        for key in current_keys:
            if key in self.__static_tracker:
                new_tracker[key] = self.__static_tracker[key] + 1
            else:
                new_tracker[key] = 1

        self.__static_tracker = new_tracker

    def _is_static_object(self, bbox):
        """Check if an object has been static for multiple frames.

        Args:
            bbox: [x, y, w, h] bounding box

        Returns:
            bool: True if object is static (appeared in same position for N+ frames)
        """
        key = self._get_bbox_key(bbox)
        count = self.__static_tracker.get(key, 0)
        return count >= self.__static_threshold

    def _encode_mask_png(self, mask):
        """Encode a binary mask as base64 PNG with alpha transparency.

        Args:
            mask (np.array): binary mask

        Returns:
            str: base64 encoded PNG string with alpha channel
        """
        # Convert binary mask to RGBA with alpha transparency
        # Object pixels = white with full opacity, background = transparent
        height, width = mask.shape
        rgba = np.zeros((height, width, 4), dtype=np.uint8)
        rgba[mask, :3] = 255  # White RGB for object pixels
        rgba[mask, 3] = 255   # Full opacity for object pixels
        # Background pixels remain (0,0,0,0) = transparent

        img = PIL.Image.fromarray(rgba, mode="RGBA")
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode("utf-8")

    def segment_single_frame(self, img):
        """Segment a single frame and return object data.

        Args:
            img (np.array): BGR image

        Returns:
            dict: segmentation results with objects, frame_blur, and image dimensions
        """
        # Get image dimensions for frontend scaling
        img_height, img_width = img.shape[:2]

        # Calculate frame-level blur
        frame_blur = planktoscope.segmenter.operations.calculate_blur(img)

        # Calculate regional blur for heatmap visualization (4x4 grid)
        blur_grid = planktoscope.segmenter.operations.calculate_regional_blur(img, 4, 4)

        # Create mask
        mask = self._create_simple_mask(img)

        # Find objects
        labels, nlabels = skimage.measure.label(mask, return_num=True)
        regionprops = skimage.measure.regionprops(labels)

        # Filter by minimum area and sort by area (largest first)
        regionprops_filtered = [
            region for region in regionprops if region.area >= self.__min_area
        ]
        regionprops_filtered.sort(key=lambda r: r.area, reverse=True)

        # Build list of all bboxes and regions for this frame
        all_bboxes = []
        bbox_region_pairs = []
        for region in regionprops_filtered:
            bbox = [
                int(region.bbox[1]),  # x
                int(region.bbox[0]),  # y
                int(region.bbox[3] - region.bbox[1]),  # width
                int(region.bbox[2] - region.bbox[0]),  # height
            ]
            all_bboxes.append(bbox)
            bbox_region_pairs.append((bbox, region))

        # Update static tracker with all detected objects BEFORE filtering
        if self.__remove_static:
            self._update_static_tracker(all_bboxes)

        # Build output objects, filtering static ones if enabled
        objects = []
        max_masks = 100

        for bbox, region in bbox_region_pairs:
            # Skip static objects (only if they've been seen for N+ consecutive frames)
            if self.__remove_static and self._is_static_object(bbox):
                continue

            obj_data = {
                "bbox": bbox,
            }

            # Include mask for objects
            if self.__overlay_mode in ("mask", "both") and len(objects) < max_masks:
                obj_data["mask"] = self._encode_mask_png(region.filled_image)

            objects.append(obj_data)

            # Limit total objects for performance
            if len(objects) >= 300:
                break

        return {
            "objects": objects,
            "frame_blur": float(frame_blur),
            "blur_grid": blur_grid,  # 4x4 regional blur heatmap
            "object_count": len(objects),  # Count after static filtering
            "image_width": img_width,
            "image_height": img_height,
        }

    def _process_captured_image(self, img_path):
        """Process a captured image from acquisition.

        Segments the image, saves object crops for visualization,
        writes TSV data, and publishes results via MQTT.

        Args:
            img_path (str): path to the captured image file
        """
        if not self.__enabled:
            return

        try:
            if not os.path.exists(img_path):
                logger.warning(f"Image file not found: {img_path}")
                return

            # FIX: Wait for file to be fully written before reading
            # The imager uses fsync, but we add a stability check as defense-in-depth
            prev_size = -1
            for _ in range(10):  # Max 500ms wait (10 * 50ms)
                try:
                    curr_size = os.path.getsize(img_path)
                    if curr_size > 0 and curr_size == prev_size:
                        break  # File size stable, safe to read
                    prev_size = curr_size
                    time.sleep(0.05)
                except OSError:
                    time.sleep(0.05)

            # Load the captured image
            frame = cv2.imread(img_path)
            if frame is None:
                logger.warning(f"Failed to load image: {img_path}")
                return

            logger.debug(f"Processing captured image: {img_path}")

            # Get acquisition info
            acq_info = self._get_acquisition_info(img_path)
            acq_folder = acq_info.get("acq_folder", "")

            # Reset counters if new acquisition
            if acq_folder != self.__current_acq_folder:
                self.__current_acq_folder = acq_folder
                self.__object_counter = 0
                self.__frame_counter = 0
                self.__static_tracker = {}

            self.__frame_counter += 1

            # Segment the frame (returns objects with bbox, mask data)
            result = self.segment_single_frame(frame)

            # Setup output directory for crops
            output_dir = self._derive_output_dir(img_path)
            if self.__save_crops:
                Path(output_dir).mkdir(parents=True, exist_ok=True)

            # Setup TSV file
            tsv_path = os.path.join(output_dir, f"ecotaxa_{acq_info['acq_id']}.tsv")
            if self.__save_crops and not os.path.exists(tsv_path):
                self._write_tsv_header(tsv_path)

            # Get base name for crops
            base_name = os.path.splitext(os.path.basename(img_path))[0]
            img_date = acq_info.get("date", "")
            img_time = "00:00:00"
            if "_" in base_name:
                time_part = base_name.split("_")[1] if len(base_name.split("_")) > 1 else ""
                if time_part:
                    img_time = time_part.replace("-", ":")[:8]

            # Re-segment to get regions for feature extraction and crop saving
            mask = self._create_simple_mask(frame)
            labels, _ = skimage.measure.label(mask, return_num=True)
            regionprops = skimage.measure.regionprops(labels)

            # Process each object in the result
            saved_crops = 0
            for obj in result.get("objects", []):
                bbox = obj.get("bbox")
                if not bbox:
                    continue

                x, y, w, h = bbox

                # Find matching region for this bbox
                matching_region = None
                for region in regionprops:
                    rx = int(region.bbox[1])
                    ry = int(region.bbox[0])
                    if abs(rx - x) < 5 and abs(ry - y) < 5:
                        matching_region = region
                        break

                if not matching_region:
                    continue

                self.__object_counter += 1
                obj_id = self.__object_counter

                # Save crop with padding
                pad = max(5, int(max(w, h) * 0.1))
                x1 = max(0, x - pad)
                y1 = max(0, y - pad)
                x2 = min(frame.shape[1], x + w + pad)
                y2 = min(frame.shape[0], y + h + pad)
                crop = frame[y1:y2, x1:x2]

                if self.__save_crops and crop.size > 0:
                    crop_filename = f"{base_name}_{obj_id}.jpg"
                    crop_path = os.path.join(output_dir, crop_filename)
                    cv2.imwrite(crop_path, crop)
                    saved_crops += 1

                    # Extract features and write TSV row
                    features = self._extract_object_features(frame, matching_region, bbox)
                    row_data = {
                        "object_id": f"{acq_info['sample_id']}_{acq_info['acq_id']}_{obj_id}",
                        "object_date": img_date,
                        "object_time": img_time,
                        "sample_id": acq_info["sample_id"],
                        "acq_id": acq_info["acq_id"],
                        "img_file_name": crop_filename,
                        **features,
                    }
                    self._append_tsv_row(tsv_path, row_data)

            # Encode the image as base64 JPEG for frontend display
            _, jpeg_buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            result["image"] = base64.b64encode(jpeg_buffer).decode("utf-8")

            # Publish results for overlay display
            self.live_client.client.publish(
                "status/segmenter/live",
                json.dumps(result, cls=planktoscope.segmenter.encoder.NpEncoder),
            )

            # Publish visualization update
            if self.__save_crops:
                self._publish_visualization_update(
                    output_dir,
                    self.__object_counter,
                    self.__frame_counter
                )

            logger.debug(f"Published segmentation: {result['object_count']} objects, {saved_crops} crops saved")

        except Exception as e:
            logger.error(f"Error processing captured image: {e}")
            import traceback
            logger.error(traceback.format_exc())

    def _check_imager_messages(self):
        """Check for new messages from the imager.

        Polls the imager MQTT client for progress events during acquisition
        and triggers segmentation when live segmentation is enabled.
        """
        if not self.imager_client.new_message_received():
            return

        try:
            message = self.imager_client.msg["payload"]
            logger.debug(f"Imager message received: {message}")
            self.imager_client.read_message()

            # Check if this is a progress event during acquisition
            # The imager publishes {"type": "progress", "path": "/path/to/image.jpeg", ...}
            if message.get("type") == "progress" and "path" in message:
                self._process_captured_image(message["path"])

        except Exception as e:
            logger.error(f"Error processing imager message: {e}")

    @logger.catch
    def treat_message(self):
        """Process incoming MQTT messages for live segmentation control."""
        if self.live_client.new_message_received():
            logger.info("Live segmenter received a new message")
            last_message = self.live_client.msg["payload"]
            logger.debug(last_message)
            self.live_client.read_message()

            if "action" in last_message:
                if last_message["action"] == "start":
                    logger.info("Enabling live segmentation overlay")
                    self.__overlay_mode = last_message.get("overlay", "bbox")

                    # Handle min_esd_um (micrometers) or fall back to min_area (pixels)
                    if "min_esd_um" in last_message:
                        min_esd = last_message.get("min_esd_um", 20)
                        self.__min_area = self._esd_um_to_min_area(min_esd)
                        logger.info(f"Minimum ESD: {min_esd} µm = {self.__min_area} pixels²")
                    else:
                        self.__min_area = last_message.get("min_area", 100)

                    # Handle remove_static option (subtract objects in same position across frames)
                    self.__remove_static = last_message.get("remove_static", True)
                    self.__static_tracker = {}  # Reset tracker on start
                    if self.__remove_static:
                        logger.info("Static object removal enabled (filtering after 3+ consecutive frames)")

                    self.__enabled = True

                    # Publish status
                    self.live_client.client.publish(
                        "status/segmenter/live",
                        json.dumps({
                            "status": "Enabled",
                            "overlay": self.__overlay_mode,
                            "min_area": self.__min_area,
                            "remove_static": self.__remove_static
                        }),
                    )

                elif last_message["action"] == "stop":
                    logger.info("Disabling live segmentation overlay")
                    self.__enabled = False
                    self.__static_tracker = {}  # Clear static tracker

                    # Clear the overlay by publishing empty objects
                    self.live_client.client.publish(
                        "status/segmenter/live",
                        json.dumps({
                            "status": "Disabled",
                            "objects": [],
                            "object_count": 0
                        }),
                    )

    @logger.catch
    def run(self):
        """Main process loop."""
        logger.info(
            f"The live segmenter control thread has been started in process {os.getpid()}"
        )

        # MQTT Client for receiving commands
        self.live_client = planktoscope.mqtt.MQTT_Client(
            topic="segmenter/live", name="live_segmenter_client"
        )

        # MQTT Client for imager status - listen for capture events
        self.imager_client = planktoscope.mqtt.MQTT_Client(
            topic="status/imager", name="live_imager_client"
        )

        # Publish ready status
        self.live_client.client.publish(
            "status/segmenter/live", '{"status":"Ready"}'
        )

        logger.success("Live Segmenter is READY!")

        # Main loop - process control messages and imager events
        while not self.stop_event.is_set():
            self.treat_message()
            self._check_imager_messages()
            time.sleep(0.05)

        logger.info("Shutting down the live segmenter process")
        self.live_client.client.publish("status/segmenter/live", '{"status":"Dead"}')
        self.live_client.shutdown()
        self.imager_client.shutdown()
        logger.success("Live segmenter process shut down! See you!")


# This guy is called if this script is launched directly
if __name__ == "__main__":
    pass
