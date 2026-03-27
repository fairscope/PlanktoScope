#!/usr/bin/env python3
"""
segment_live.py - Live segmentation for PlanktoScope with Real-time Visualization

Features:
- Saves object crops to /home/pi/data/objects
- Generates _debug.jpg for dashboard preview
- Writes EcoTaxa-compatible TSV incrementally for visualization
- Publishes MQTT updates for live dashboard refresh
- Supports all segmentation methods (hierarchical, planktoscope, opencv, watershed, auto)
- Background subtraction for stuck particle removal
- Flat field correction recalculated every 25 frames using 3 reference frames
"""

import json
import os
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

# Force unbuffered stdout for Node-RED exec node
sys.stdout.reconfigure(line_buffering=True)

#
# CONFIGURATION


PARAMS_FILE_TEMP = "/tmp/seg_params.json"
PARAMS_FILE_TUNER = "/home/pi/PlanktoScope/segmentation_params.json"
IMG_BASE = "/home/pi/data/img"
SEGMENTED_BASE = "/home/pi/data/objects"
ECOTAXA_BASE = "/home/pi/data/export/ecotaxa"

# Background subtraction persistence files
PREVIOUS_MASK_FILE = "/tmp/seg_previous_mask.npy"
PREVIOUS_ACQ_FILE = "/tmp/seg_previous_acq.txt"

# Live stats tracking (persists across frames in same acquisition)
LIVE_STATS_FILE = "/tmp/seg_live_stats.json"

# Metrics log file (JSONL format for analysis)
METRICS_LOG_FILE = "/tmp/seg_metrics.jsonl"

# Flat field state tracking
FLATFIELD_STATE_FILE = "/tmp/seg_flatfield_state.json"
FLATFIELD_RECALC_INTERVAL = 25  # Recalculate every 25 frames
FLATFIELD_REF_FRAMES = 3  # Use 3 frames for calculation

# Default segmentation parameters
DEFAULT_PARAMS = {
    "segmentation_method": "planktoscope",
    "min_diameter": 20,
    "pixel_size": 0.94,
    "threshold_method": "otsu",
    "solidity_threshold": 0.85,
    "overlap_threshold": 0.3,
    "expand_bbox_factor": 0.1,
    "use_clahe": False,
    "remove_previous": True,  # Enable background subtraction
    "use_flatfield": True,  # Enable flat field correction
}

# EcoTaxa TSV column headers
ECOTAXA_COLUMNS = [
    "object_id",
    "object_date",
    "object_time",
    "object_lat",
    "object_lon",
    "object_depth_min",
    "object_depth_max",
    "object_label",
    "object_bx",
    "object_by",
    "object_x",
    "object_y",
    "object_width",
    "object_height",
    "object_area",
    "object_area_exc",
    "object_%area",
    "object_perim.",
    "object_major",
    "object_minor",
    "object_circ.",
    "object_circex",
    "object_elongation",
    "object_solidity",
    "object_eccentricity",
    "object_equivalent_diameter",
    "object_convex_area",
    "object_bounding_box_area",
    "object_angle",
    "object_perimareaexc",
    "object_perimmajor",
    "object_euler_number",
    "object_extent",
    "object_local_centroid_col",
    "object_local_centroid_row",
    "object_MeanHue",
    "object_MeanSaturation",
    "object_MeanValue",
    "object_StdHue",
    "object_StdSaturation",
    "object_StdValue",
    "sample_id",
    "sample_project",
    "acq_id",
    "process_pixel",
    "img_file_name",
    "object_blur_score",
    "object_blur_laplacian",
    "object_blur_tenengrad",
    "object_blur_confidence",
]


#
# UTILITY FUNCTIONS


def derive_output_dir(image_path):
    """Mirror the img folder structure into the objects folder."""
    abs_path = os.path.abspath(image_path)
    img_dir = os.path.dirname(abs_path)

    if img_dir.startswith(IMG_BASE):
        rel_path = os.path.relpath(img_dir, IMG_BASE)
        return os.path.join(SEGMENTED_BASE, rel_path)
    else:
        return os.path.join(img_dir, "objects")


def get_acquisition_info(image_path):
    """
    Extract acquisition info from image path.
    Path format: /home/pi/data/img/DATE/PROJECT_SAMPLE/PROJECT_SAMPLE_ACQ/image.jpg
    """
    try:
        parts = image_path.split("/")
        if "img" in parts:
            idx = parts.index("img")
            date_folder = parts[idx + 1] if len(parts) > idx + 1 else ""
            sample_folder = parts[idx + 2] if len(parts) > idx + 2 else ""
            acq_folder = parts[idx + 3] if len(parts) > idx + 3 else ""

            # Parse project from sample folder
            sample_parts = sample_folder.rsplit("_", 1)
            project = sample_parts[0] if len(sample_parts) > 1 else sample_folder

            # Parse acquisition number
            acq_match = acq_folder.rsplit("_", 1)
            acq_num = acq_match[-1] if acq_match else "0"
            acq_id = f"A_{acq_num}" if not acq_num.startswith("A_") else acq_num

            return {
                "date": date_folder,
                "sample_id": sample_folder,
                "acq_id": acq_id,
                "project": project,
                "acq_folder": acq_folder,
            }
    except Exception:
        pass

    return {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "sample_id": "unknown",
        "acq_id": "A_0",
        "project": "unknown",
        "acq_folder": "unknown",
    }


def load_params():
    """Load segmentation parameters from temp file or tuner config."""
    params = DEFAULT_PARAMS.copy()

    if os.path.exists(PARAMS_FILE_TEMP):
        try:
            with open(PARAMS_FILE_TEMP, "r") as f:
                params.update(json.load(f))
            os.remove(PARAMS_FILE_TEMP)
        except Exception:
            pass
    elif os.path.exists(PARAMS_FILE_TUNER):
        try:
            with open(PARAMS_FILE_TUNER, "r") as f:
                params.update(json.load(f))
        except Exception:
            pass

    return params


#
# LIVE STATS TRACKING


def load_live_stats(acq_folder):
    """Load running stats for this acquisition."""
    try:
        if os.path.exists(LIVE_STATS_FILE):
            with open(LIVE_STATS_FILE, "r") as f:
                stats = json.load(f)
            if stats.get("acq_folder") == acq_folder:
                return stats
    except Exception:
        pass

    # New acquisition - reset stats
    return {
        "acq_folder": acq_folder,
        "total_objects": 0,
        "total_images": 0,
        "object_id_counter": 0,
    }


def save_live_stats(stats):
    """Save running stats to file."""
    try:
        with open(LIVE_STATS_FILE, "w") as f:
            json.dump(stats, f)
    except Exception:
        pass


def log_metrics(metrics):
    """Append metrics to JSONL log file for analysis."""
    try:
        with open(METRICS_LOG_FILE, "a") as f:
            f.write(json.dumps(metrics) + "\n")
    except Exception:
        pass


def clear_metrics_log(acq_folder):
    """Clear metrics log when starting a new acquisition."""
    try:
        # Check if this is a new acquisition
        if os.path.exists(METRICS_LOG_FILE):
            with open(METRICS_LOG_FILE, "r") as f:
                first_line = f.readline()
                if first_line:
                    data = json.loads(first_line)
                    if data.get("acq_folder") != acq_folder:
                        # New acquisition - clear the log
                        os.remove(METRICS_LOG_FILE)
    except Exception:
        pass


#
# FLAT FIELD CORRECTION


def load_flatfield_state(acq_folder):
    """Load or initialize flat field state for this acquisition."""
    try:
        if os.path.exists(FLATFIELD_STATE_FILE):
            with open(FLATFIELD_STATE_FILE, "r") as f:
                state = json.load(f)
            if state.get("acq_folder") == acq_folder:
                return state
    except Exception:
        pass

    # New acquisition - reset flat field state
    return {
        "frame_count": 0,
        "acq_folder": acq_folder,
        "flatfield_frames": [],  # Paths to last 3 frames
        "flatfield_ref": None,  # Cached reference path (.npy file)
    }


def save_flatfield_state(state):
    """Persist flat field state to file."""
    try:
        with open(FLATFIELD_STATE_FILE, "w") as f:
            json.dump(state, f)
    except Exception:
        pass


def calculate_flatfield(frame_paths):
    """
    Calculate flat field from 3 reference frames using median.

    Args:
        frame_paths: List of paths to reference frame images

    Returns:
        Flat field reference array (float32) or None if calculation fails
    """
    import cv2
    import numpy as np

    if len(frame_paths) < FLATFIELD_REF_FRAMES:
        return None

    frames = []
    for path in frame_paths[-FLATFIELD_REF_FRAMES:]:
        if os.path.exists(path):
            img = cv2.imread(path)
            if img is not None:
                frames.append(img.astype(np.float32))

    if len(frames) < FLATFIELD_REF_FRAMES:
        return None

    # Calculate median across frames (reduces influence of objects)
    stacked = np.stack(frames, axis=0)
    flat_ref = np.median(stacked, axis=0)

    # Normalize to prevent division issues
    flat_ref = np.clip(flat_ref, 1, 255)

    return flat_ref


def apply_flatfield(image, flat_ref):
    """
    Apply flat field correction to an image.

    Args:
        image: BGR image (numpy array, uint8)
        flat_ref: Flat field reference (float32)

    Returns:
        Corrected image (uint8)
    """
    import numpy as np

    if flat_ref is None:
        return image

    # Apply flat field correction matching the main PlanktoScope codebase:
    # image = image / flat, then rescale_intensity to uint8
    import skimage.exposure

    corrected = image / flat_ref

    # Adding one black pixel top left (matches main codebase)
    corrected[0][0] = [0, 0, 0]

    corrected = skimage.exposure.rescale_intensity(
        corrected, in_range=(0, 1.04), out_range="uint8"
    )

    return corrected


#
# BACKGROUND SUBTRACTION (Stuck Particle Removal)


def load_previous_mask(image_path):
    """Load previous frame's mask if from same acquisition."""
    import numpy as np

    acq_info = get_acquisition_info(image_path)
    current_acq = acq_info.get("acq_folder", "")

    # Check if previous mask is from same acquisition
    if os.path.exists(PREVIOUS_ACQ_FILE):
        try:
            with open(PREVIOUS_ACQ_FILE, "r") as f:
                stored_acq = f.read().strip()
            if stored_acq != current_acq:
                clear_previous_mask()
                return None
        except Exception:
            pass

    # Load the mask
    if os.path.exists(PREVIOUS_MASK_FILE):
        try:
            return np.load(PREVIOUS_MASK_FILE)
        except Exception:
            pass

    return None


def save_previous_mask(mask, image_path):
    """Save current mask for next frame's background subtraction."""
    import numpy as np

    try:
        np.save(PREVIOUS_MASK_FILE, mask)
        acq_info = get_acquisition_info(image_path)
        with open(PREVIOUS_ACQ_FILE, "w") as f:
            f.write(acq_info.get("acq_folder", ""))
    except Exception:
        pass


def clear_previous_mask():
    """Clear saved mask files."""
    for f in [PREVIOUS_MASK_FILE, PREVIOUS_ACQ_FILE]:
        try:
            if os.path.exists(f):
                os.remove(f)
        except Exception:
            pass


def apply_background_subtraction(binary_mask, image_path, params):
    """
    Apply background subtraction using previous frame's mask.
    Returns: (processed_mask, was_subtracted)
    """
    import numpy as np

    if not params.get("remove_previous", True):
        return binary_mask, False

    previous_mask = load_previous_mask(image_path)
    subtracted = False

    if previous_mask is not None and previous_mask.shape == binary_mask.shape:
        # Remove pixels that were also in previous frame (stuck particles)
        overlap = binary_mask & previous_mask
        binary_mask = binary_mask & ~overlap
        subtracted = True

    # Save current mask for next frame
    save_previous_mask(binary_mask.copy(), image_path)

    return binary_mask, subtracted


#
# MQTT PUBLISHING


def publish_mqtt_status(stats, output_dir):
    """Publish segmentation status via MQTT for live visualization."""
    try:
        import paho.mqtt.publish as publish

        message = {
            "status": "segmenting",
            "total_objects": stats.get("total_objects", 0),
            "total_images": stats.get("total_images", 0),
            "output_dir": output_dir,
            "timestamp": time.time(),
        }

        publish.single(
            "status/segmentation",
            payload=json.dumps(message),
            hostname="localhost",
            port=1883,
            qos=0,
        )
    except ImportError:
        # paho-mqtt not installed - skip silently
        pass
    except Exception:
        # MQTT publish failed - non-fatal
        pass


#
# TSV WRITING


def extract_object_features(img, mask, bbox, obj_id):
    """Extract EcoTaxa-compatible morphological features from an object."""
    import cv2
    import numpy as np

    x, y, w, h = bbox

    # Extract ROI
    roi_mask = mask[y : y + h, x : x + w] if mask is not None else None
    roi_img = img[y : y + h, x : x + w]

    # Calculate area
    if roi_mask is not None:
        area = int(np.sum(roi_mask > 0))
    else:
        area = w * h

    if area == 0:
        return None

    # Find contours
    if roi_mask is not None:
        contours, _ = cv2.findContours(roi_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return None
        cnt = max(contours, key=cv2.contourArea)
        perimeter = cv2.arcLength(cnt, True)
    else:
        perimeter = 2 * (w + h)
        cnt = None

    # Centroid
    cx, cy = w / 2, h / 2
    if roi_mask is not None:
        M = cv2.moments(roi_mask)
        if M["m00"] > 0:
            cx = M["m10"] / M["m00"]
            cy = M["m01"] / M["m00"]

    # Ellipse fitting for major/minor axes
    major, minor = max(w, h), min(w, h)
    if cnt is not None and len(cnt) >= 5:
        try:
            ellipse = cv2.fitEllipse(cnt)
            (_, (minor_ax, major_ax), _) = ellipse
            major, minor = max(major_ax, minor_ax), min(major_ax, minor_ax)
        except Exception:
            pass

    # Convex hull for solidity
    solidity = 1.0
    if cnt is not None:
        hull = cv2.convexHull(cnt)
        hull_area = cv2.contourArea(hull)
        if hull_area > 0:
            solidity = min(1.0, area / hull_area)

    # Derived metrics
    circularity = (4 * 3.14159 * area / (perimeter**2)) if perimeter > 0 else 0
    elongation = major / minor if minor > 0 else 1.0
    equivalent_diameter = (4 * area / 3.14159) ** 0.5
    eccentricity = ((major**2 - minor**2) ** 0.5 / major) if major > minor else 0

    # HSV color statistics
    mean_hue, mean_sat, mean_val = 0, 0, 0
    std_hue, std_sat, std_val = 0, 0, 0

    try:
        roi_hsv = cv2.cvtColor(roi_img, cv2.COLOR_BGR2HSV)
        if roi_mask is not None:
            mask_bool = roi_mask > 0
            if np.any(mask_bool):
                h_vals = roi_hsv[:, :, 0][mask_bool]
                s_vals = roi_hsv[:, :, 1][mask_bool]
                v_vals = roi_hsv[:, :, 2][mask_bool]
                mean_hue, std_hue = float(np.mean(h_vals)), float(np.std(h_vals))
                mean_sat, std_sat = float(np.mean(s_vals)), float(np.std(s_vals))
                mean_val, std_val = float(np.mean(v_vals)), float(np.std(v_vals))
        else:
            mean_hue = float(np.mean(roi_hsv[:, :, 0]))
            mean_sat = float(np.mean(roi_hsv[:, :, 1]))
            mean_val = float(np.mean(roi_hsv[:, :, 2]))
    except Exception:
        pass

    # Blur analysis
    blur_score, blur_laplacian, blur_tenengrad, blur_confidence = 0, 0, 0, 0
    try:
        from blur_metrics import get_blur_metrics

        blur_result = get_blur_metrics(roi_img, roi_mask)
        blur_score = blur_result.get("blur_score", 0)
        blur_laplacian = blur_result.get("laplacian_var", 0)
        blur_tenengrad = blur_result.get("tenengrad", 0)
        blur_confidence = blur_result.get("confidence", 0)
    except Exception:
        pass  # Blur metrics optional - don't fail segmentation

    return {
        "object_x": x + cx,
        "object_y": y + cy,
        "object_width": w,
        "object_height": h,
        "object_area": area,
        "object_area_exc": area,
        "object_perim.": perimeter,
        "object_major": major,
        "object_minor": minor,
        "object_circ.": circularity,
        "object_elongation": elongation,
        "object_solidity": solidity,
        "object_eccentricity": eccentricity,
        "object_equivalent_diameter": equivalent_diameter,
        "object_MeanHue": mean_hue,
        "object_MeanSaturation": mean_sat,
        "object_MeanValue": mean_val,
        "object_StdHue": std_hue,
        "object_StdSaturation": std_sat,
        "object_StdValue": std_val,
        "object_blur_score": blur_score,
        "object_blur_laplacian": blur_laplacian,
        "object_blur_tenengrad": blur_tenengrad,
        "object_blur_confidence": blur_confidence,
    }


def write_tsv_header(tsv_path):
    """Write EcoTaxa TSV header."""
    try:
        with open(tsv_path, "w") as f:
            # Header row
            f.write("\t".join(ECOTAXA_COLUMNS) + "\n")
            # Type indicator row (all text for simplicity)
            types = ["[t]"] * len(ECOTAXA_COLUMNS)
            f.write("\t".join(types) + "\n")
        return True
    except Exception:
        return False


def append_tsv_row(tsv_path, row_data):
    """Append a single row to the TSV file."""
    try:
        with open(tsv_path, "a") as f:
            values = []
            for col in ECOTAXA_COLUMNS:
                val = row_data.get(col, "")
                if isinstance(val, float):
                    values.append(f"{val:.6f}")
                else:
                    values.append(str(val))
            f.write("\t".join(values) + "\n")
        return True
    except Exception:
        return False


#
# SEGMENTATION METHODS


def run_hierarchical(image_path, params, img=None):
    """Run hierarchical segmentation method."""
    try:
        from planktoscope_classifier_hierarchical_v5 import (
            PlanktoScopeHierarchicalClassifier,
        )

        classifier = PlanktoScopeHierarchicalClassifier()
        result = classifier.segment_and_extract(image_path, params, img=img)
        if result.get("status") == "success":
            result["method"] = "hierarchical"
        return result
    except ImportError as e:
        return {
            "status": "error",
            "error": f"Hierarchical import failed: {e}",
            "objects": [],
        }
    except Exception as e:
        return {"status": "error", "error": f"Hierarchical failed: {e}", "objects": []}


def run_planktoscope_original(image_path, params, img=None):
    """Run original PlanktoScope segmentation with background subtraction support."""
    try:
        from planktoscope_segmenter_original import PlanktoScopeOriginalSegmenter

        segmenter = PlanktoScopeOriginalSegmenter()

        # Load previous mask for background subtraction
        if params.get("remove_previous", True):
            prev_mask = load_previous_mask(image_path)
            if prev_mask is not None:
                segmenter.previous_mask = prev_mask

        result = segmenter.segment_and_extract(image_path, params, img=img)

        # Save mask for next frame
        if result.get("status") == "success" and params.get("remove_previous", True):
            if hasattr(segmenter, "previous_mask") and segmenter.previous_mask is not None:
                save_previous_mask(segmenter.previous_mask, image_path)

        if result.get("status") == "success":
            result["method"] = "planktoscope"
        return result
    except ImportError as e:
        return {
            "status": "error",
            "error": f"PlanktoScope import failed: {e}",
            "objects": [],
        }
    except Exception as e:
        return {"status": "error", "error": f"PlanktoScope failed: {e}", "objects": []}


def run_opencv_simple(image_path, params, img=None):
    """Run simple OpenCV threshold-based segmentation."""
    import cv2
    import numpy as np

    try:
        if img is None:
            img = cv2.imread(image_path)
        if img is None:
            return {"status": "error", "error": "Could not load image", "objects": []}

        # Convert to grayscale and threshold
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        _, binary = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

        # Morphological cleanup
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=2)
        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel, iterations=1)

        # Apply background subtraction
        binary, _ = apply_background_subtraction(binary, image_path, params)

        # Find contours
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # Filter by minimum size
        min_diameter = params.get("min_diameter", 20)
        pixel_size = params.get("pixel_size", 0.94)
        min_area = 3.14159 * (min_diameter / (2 * pixel_size)) ** 2

        objects = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < min_area:
                continue

            x, y, w, h = cv2.boundingRect(cnt)
            objects.append(
                {
                    "id": len(objects) + 1,
                    "bbox": {"x": x, "y": y, "width": w, "height": h},
                    "area_px": area,
                }
            )

        return {
            "status": "success",
            "objects": objects,
            "method": "opencv",
            "mask": binary,
        }
    except Exception as e:
        return {"status": "error", "error": f"OpenCV failed: {e}", "objects": []}


def run_watershed(image_path, params, img=None):
    """Run watershed-based segmentation for touching objects."""
    import cv2
    import numpy as np

    try:
        if img is None:
            img = cv2.imread(image_path)
        if img is None:
            return {"status": "error", "error": "Could not load image", "objects": []}

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

        # Apply background subtraction first
        binary, _ = apply_background_subtraction(binary, image_path, params)

        # Distance transform for watershed seeds
        dist = cv2.distanceTransform(binary, cv2.DIST_L2, 5)
        _, sure_fg = cv2.threshold(dist, 0.3 * dist.max(), 255, 0)
        sure_fg = sure_fg.astype(np.uint8)

        # Background region
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        sure_bg = cv2.dilate(binary, kernel, iterations=3)
        unknown = cv2.subtract(sure_bg, sure_fg)

        # Markers for watershed
        num_labels, markers = cv2.connectedComponents(sure_fg)
        markers = markers + 1
        markers[unknown == 255] = 0
        markers = cv2.watershed(img, markers)

        # Extract objects from watershed result
        min_diameter = params.get("min_diameter", 20)
        pixel_size = params.get("pixel_size", 0.94)
        min_area = 3.14159 * (min_diameter / (2 * pixel_size)) ** 2

        objects = []
        for label_id in range(2, num_labels + 2):
            label_mask = (markers == label_id).astype(np.uint8) * 255
            contours, _ = cv2.findContours(label_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            if not contours:
                continue

            cnt = max(contours, key=cv2.contourArea)
            area = cv2.contourArea(cnt)

            if area < min_area:
                continue

            x, y, w, h = cv2.boundingRect(cnt)
            objects.append(
                {
                    "id": len(objects) + 1,
                    "bbox": {"x": x, "y": y, "width": w, "height": h},
                    "area_px": area,
                }
            )

        return {
            "status": "success",
            "objects": objects,
            "method": "watershed",
            "mask": binary,
        }
    except Exception as e:
        return {"status": "error", "error": f"Watershed failed: {e}", "objects": []}


# MAIN FUNCTION


def main():
    try:
        # 1. Parse Arguments
        if len(sys.argv) < 2:
            print(json.dumps({"error": "Usage: segment_live.py <image_path> [output_dir]"}))
            return

        image_path = sys.argv[1]
        output_dir = sys.argv[2] if len(sys.argv) >= 3 else derive_output_dir(image_path)
        # Ensure output_dir is absolute
        if not output_dir.startswith("/"):
            output_dir = derive_output_dir(image_path)

        if not os.path.exists(image_path):
            print(json.dumps({"error": f"Image not found: {image_path}"}))
            return

        # 2. Import heavy libraries
        import cv2
        import numpy as np

        sys.path.insert(0, "/home/pi/PlanktoScope/segmenter")

        # 3. Load parameters and image
        params = load_params()
        img = cv2.imread(image_path)
        if img is None:
            print(json.dumps({"error": "Could not read image file"}))
            return

        # 4. Get acquisition info and load stats
        acq_info = get_acquisition_info(image_path)
        acq_folder = acq_info.get("acq_folder", "")
        stats = load_live_stats(acq_folder)

        # Clear metrics log if this is a new acquisition
        if stats["total_images"] == 0:
            clear_metrics_log(acq_folder)

        # 5. Flat field correction
        if params.get("use_flatfield", True):
            ff_state = load_flatfield_state(acq_folder)
            ff_state["frame_count"] += 1

            # Store current frame path for flat field calculation
            ff_state["flatfield_frames"].append(image_path)
            if len(ff_state["flatfield_frames"]) > FLATFIELD_REF_FRAMES:
                ff_state["flatfield_frames"] = ff_state["flatfield_frames"][-FLATFIELD_REF_FRAMES:]

            # Calculate flat field as soon as we have enough reference frames,
            # then recalculate every FLATFIELD_RECALC_INTERVAL frames after that.
            # This ensures stuck objects are normalized out from the very first frames.
            needs_initial = (
                ff_state.get("flatfield_ref") is None
                and ff_state["frame_count"] >= FLATFIELD_REF_FRAMES
            )
            needs_recalc = (
                ff_state["frame_count"] >= FLATFIELD_REF_FRAMES
                and ff_state["frame_count"] % FLATFIELD_RECALC_INTERVAL == 0
            )
            if needs_initial or needs_recalc:
                flat_ref = calculate_flatfield(ff_state["flatfield_frames"])
                if flat_ref is not None:
                    # Save flat reference to file in acquisition folder
                    acq_dir = os.path.dirname(image_path)
                    flat_path = os.path.join(acq_dir, ".flatfield_ref.npy")
                    np.save(flat_path, flat_ref)
                    ff_state["flatfield_ref"] = flat_path

            # Apply flat field correction if available
            if ff_state.get("flatfield_ref") and os.path.exists(ff_state["flatfield_ref"]):
                try:
                    flat_ref = np.load(ff_state["flatfield_ref"])
                    img = apply_flatfield(img, flat_ref)
                except Exception:
                    pass  # Continue without flat field if loading fails

            # Save flat field state
            save_flatfield_state(ff_state)

        # 6. Run segmentation
        method = params.get("segmentation_method", "hierarchical")
        start_time = time.time()
        seg_result = None

        # Method dispatch - pass corrected image to avoid re-reading
        if method == "hierarchical":
            seg_result = run_hierarchical(image_path, params, img=img)
        elif method == "planktoscope":
            seg_result = run_planktoscope_original(image_path, params, img=img)
        elif method == "opencv":
            seg_result = run_opencv_simple(image_path, params, img=img)
        elif method == "watershed":
            seg_result = run_watershed(image_path, params, img=img)
        elif method == "auto":
            # Try methods in order of preference
            for fn in [run_hierarchical, run_planktoscope_original, run_opencv_simple]:
                seg_result = fn(image_path, params, img=img)
                if seg_result.get("status") == "success":
                    break
        else:
            # Default to hierarchical
            seg_result = run_hierarchical(image_path, params, img=img)

        # Fallback chain if primary method failed
        if seg_result is None or seg_result.get("status") != "success":
            for fallback in [run_planktoscope_original, run_opencv_simple]:
                seg_result = fallback(image_path, params, img=img)
                if seg_result.get("status") == "success":
                    break

        if seg_result is None or seg_result.get("status") != "success":
            error_msg = seg_result.get("error", "All methods failed") if seg_result else "No result"
            print(json.dumps({"error": f"Segmentation failed: {error_msg}"}))
            return

        objects = seg_result.get("objects", [])
        mask = seg_result.get("mask")
        actual_method = seg_result.get("method", method)

        # 7. Create output directories
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        base_name = os.path.splitext(os.path.basename(image_path))[0]

        # 8. Setup EcoTaxa TSV file
        # TSV goes to the same folder as objects: /home/pi/data/objects/{date}/{sample}/{acq}/ecotaxa_{acq}.tsv
        # IMPORTANT: db.js expects TSV filename to match the directory name, not just acq_id
        # e.g., for /home/pi/data/objects/2026-02-13/proj_sample/proj_sample_A_1/
        # db.js looks for ecotaxa_proj_sample_A_1.tsv (using full folder name)
        folder_name = os.path.basename(output_dir)  # Gets "proj_sample_A_1" from path
        tsv_filename = f"ecotaxa_{folder_name}.tsv"
        tsv_path = os.path.join(output_dir, tsv_filename)

        # Also create a copy in export/ecotaxa for EcoTaxa compatibility
        ecotaxa_export_dir = os.path.join(ECOTAXA_BASE, acq_info["sample_id"])
        Path(ecotaxa_export_dir).mkdir(parents=True, exist_ok=True)
        ecotaxa_export_tsv = os.path.join(ecotaxa_export_dir, f"ecotaxa_{acq_info['sample_id']}_{acq_info['acq_id']}.tsv")

        # Write header if new file (main TSV for visualizer)
        if not os.path.exists(tsv_path):
            write_tsv_header(tsv_path)

        # Write header for EcoTaxa export copy
        if not os.path.exists(ecotaxa_export_tsv):
            write_tsv_header(ecotaxa_export_tsv)

        # Parse timestamp from filename (YYYY-MM-DD_HH-MM-SS-ffffff.jpg)
        img_date = acq_info.get("date", "")
        img_time = "00:00:00"
        if "_" in base_name:
            time_part = base_name.split("_")[1] if len(base_name.split("_")) > 1 else ""
            if time_part:
                img_time = time_part.replace("-", ":")[:8]

        # 9. Update stats
        stats["total_images"] += 1

        # 10. Process and save each object
        saved_count = 0
        for i, obj in enumerate(objects):
            bbox = obj.get("bbox", {})
            x = int(bbox.get("x", 0))
            y = int(bbox.get("y", 0))
            w = int(bbox.get("width", 0))
            h = int(bbox.get("height", 0))

            # Increment counters
            stats["object_id_counter"] += 1
            stats["total_objects"] += 1
            global_obj_id = stats["object_id_counter"]

            # Save crop: use expanded_slice (10px padding, matching main codebase)
            # if provided by planktoscope method, otherwise fall back to bbox expansion
            expanded_slice = obj.get("expanded_slice")
            if expanded_slice is not None:
                crop = img[expanded_slice]
            else:
                expand_factor = params.get("expand_bbox_factor", 0.1)
                pad_x = int(w * expand_factor / 2)
                pad_y = int(h * expand_factor / 2)
                x_exp = max(0, x - pad_x)
                y_exp = max(0, y - pad_y)
                w_exp = min(w + 2 * pad_x, img.shape[1] - x_exp)
                h_exp = min(h + 2 * pad_y, img.shape[0] - y_exp)
                if w_exp <= 0 or h_exp <= 0:
                    continue
                crop = img[y_exp : y_exp + h_exp, x_exp : x_exp + w_exp]

            crop_filename = f"{base_name}_{global_obj_id}.jpg"
            cv2.imwrite(os.path.join(output_dir, crop_filename), crop)
            saved_count += 1

            # Use regionprops-based features if provided by planktoscope method,
            # otherwise fall back to manual extraction
            obj_features = obj.get("features")
            if obj_features:
                # Map regionprops feature keys to object_* TSV column names
                features = {}
                for k, v in obj_features.items():
                    features[f"object_{k}"] = v
            else:
                features = extract_object_features(img, mask, (x, y, w, h), global_obj_id)

            # Compute blur metrics for the crop
            blur_score, blur_laplacian, blur_tenengrad, blur_confidence = 0, 0, 0, 0
            try:
                from blur_metrics import get_blur_metrics
                roi_mask_for_blur = mask[y:y+h, x:x+w] if mask is not None else None
                blur_result = get_blur_metrics(img[y:y+h, x:x+w], roi_mask_for_blur)
                blur_score = blur_result.get("blur_score", 0)
                blur_laplacian = blur_result.get("laplacian_var", 0)
                blur_tenengrad = blur_result.get("tenengrad", 0)
                blur_confidence = blur_result.get("confidence", 0)
            except Exception:
                pass

            if features:
                row_data = {
                    "object_id": f"{acq_info['sample_id']}_{acq_info['acq_id']}_{global_obj_id}",
                    "object_date": img_date,
                    "object_time": img_time,
                    "object_lat": 0,
                    "object_lon": 0,
                    "object_depth_min": 0,
                    "object_depth_max": 0,
                    "sample_id": acq_info["sample_id"],
                    "sample_project": acq_info["project"],
                    "acq_id": acq_info["acq_id"],
                    "process_pixel": params.get("pixel_size", 0.94),
                    "img_file_name": crop_filename,
                    "object_blur_score": blur_score,
                    "object_blur_laplacian": blur_laplacian,
                    "object_blur_tenengrad": blur_tenengrad,
                    "object_blur_confidence": blur_confidence,
                    **features,
                }
                append_tsv_row(tsv_path, row_data)
                append_tsv_row(ecotaxa_export_tsv, row_data)  # Copy for EcoTaxa export

        # 11. Save debug visualization
        vis_img = img.copy()
        for obj in objects:
            bbox = obj.get("bbox", {})
            x, y = int(bbox.get("x", 0)), int(bbox.get("y", 0))
            w, h = int(bbox.get("width", 0)), int(bbox.get("height", 0))
            cv2.rectangle(vis_img, (x, y), (x + w, y + h), (0, 255, 0), 4)

        debug_path = image_path.replace(".jpg", "_debug.jpg")
        cv2.imwrite(debug_path, vis_img)

        # 12. Save stats and publish MQTT
        save_live_stats(stats)
        publish_mqtt_status(stats, output_dir)

        # 13. Output result
        end_time = time.time()
        processing_time_ms = int((end_time - start_time) * 1000)

        result = {
            "status": "success",
            "objects_found": len(objects),
            "crops_saved": saved_count,
            "processing_time_ms": processing_time_ms,
            "output_dir": output_dir,
            "method": actual_method,
            "tsv_path": tsv_path,
            "total_objects": stats["total_objects"],
            "total_images": stats["total_images"],
        }
        print(json.dumps(result))

        # 14. Log metrics for analysis
        metrics = {
            "timestamp": end_time,
            "acq_folder": acq_folder,
            "image": os.path.basename(image_path),
            "processing_time_ms": processing_time_ms,
            "objects_found": len(objects),
            "crops_saved": saved_count,
            "method": actual_method,
            "image_index": stats["total_images"],
            "cumulative_objects": stats["total_objects"],
        }
        log_metrics(metrics)

    except Exception as e:
        print(
            json.dumps(
                {
                    "error": f"Critical error: {str(e)}",
                    "traceback": traceback.format_exc(),
                }
            )
        )


if __name__ == "__main__":
    main()
