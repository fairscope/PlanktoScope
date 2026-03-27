"""segment_worker.py - Pool-compatible worker for live per-frame segmentation.

This module provides a top-level function that can be submitted to a
ProcessPoolExecutor from the imager controller. It segments a single frame
using the planktoscope pipeline (flat field correction, threshold, morphological
ops, regionprop extraction, object cropping, incremental EcoTaxa TSV writing).

The function is intentionally kept at module level (no closures, no unpicklable
state) so it can be pickled and sent to worker processes.
"""

import json
import os
import time
from pathlib import Path

import cv2
import numpy as np
import skimage.exposure
import skimage.measure
from loguru import logger


# EcoTaxa TSV column headers (matches batch segmenter output)
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
    "object_blur_laplacian",
    "sample_id",
    "sample_project",
    "acq_id",
    "process_pixel",
    "img_file_name",
]


def _apply_flat_field(image: np.ndarray, flat_ref: np.ndarray) -> np.ndarray:
    """Apply flat field correction to an image.

    Uses the same algorithm as the batch segmenter: image / flat, rescale_intensity.
    """
    corrected = image / flat_ref
    # Adding one black pixel top left (matches batch segmenter)
    corrected[0][0] = [0, 0, 0]
    corrected = skimage.exposure.rescale_intensity(corrected, in_range=(0, 1.04), out_range="uint8")
    return corrected


def _create_mask(gray_img: np.ndarray) -> np.ndarray:
    """Create a binary mask using the planktoscope threshold pipeline.

    Replicates the batch segmenter's _create_mask pipeline:
    simple_threshold -> erode -> dilate -> close -> erode2
    """
    # Simple threshold (Otsu)
    _, mask = cv2.threshold(gray_img, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    # Erode
    kernel_erode = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2, 2))
    mask = cv2.erode(mask, kernel_erode)

    # Dilate
    kernel_dilate = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (4, 4))
    mask = cv2.dilate(mask, kernel_dilate)

    # Close
    kernel_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (4, 4))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel_close)

    # Erode2
    kernel_erode2 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2, 2))
    mask = cv2.erode(mask, kernel_erode2)

    return mask


def _extract_metadata_from_regionprop(prop, pixel_size_um=None):
    """Extract morphological metadata from a scikit-image regionprop.

    Identical to the batch segmenter's calibrated extraction.
    """
    px = pixel_size_um if pixel_size_um and pixel_size_um > 0 else 1.0
    px2 = px * px

    return {
        "label": prop.label,
        "width": (prop.bbox[3] - prop.bbox[1]) * px,
        "height": (prop.bbox[2] - prop.bbox[0]) * px,
        "bx": prop.bbox[1],
        "by": prop.bbox[0],
        "circ.": (4 * np.pi * prop.filled_area) / prop.perimeter**2,
        "area_exc": prop.area * px2,
        "area": prop.filled_area * px2,
        "%area": 1 - (prop.area / prop.filled_area),
        "major": prop.major_axis_length * px,
        "minor": prop.minor_axis_length * px,
        "y": prop.centroid[0],
        "x": prop.centroid[1],
        "convex_area": prop.convex_area * px2,
        "perim.": prop.perimeter * px,
        "elongation": np.divide(prop.major_axis_length, prop.minor_axis_length),
        "perimareaexc": prop.perimeter / prop.area * (1.0 / px),
        "perimmajor": prop.perimeter / prop.major_axis_length,
        "circex": np.divide(4 * np.pi * prop.area, prop.perimeter**2),
        "angle": prop.orientation / np.pi * 180 + 90,
        "bounding_box_area": prop.bbox_area * px2,
        "eccentricity": prop.eccentricity,
        "equivalent_diameter": prop.equivalent_diameter * px,
        "euler_number": prop.euler_number,
        "extent": prop.extent,
        "local_centroid_col": prop.local_centroid[1],
        "local_centroid_row": prop.local_centroid[0],
        "solidity": prop.solidity,
    }


def _get_color_info(bgr_img, mask):
    """Extract HSV color statistics from an object image."""
    hsv_img = cv2.cvtColor(bgr_img, cv2.COLOR_BGR2HSV)
    (h_channel, s_channel, v_channel) = cv2.split(hsv_img)
    return {
        "MeanHue": np.mean(h_channel, where=mask),
        "MeanSaturation": np.mean(s_channel, where=mask),
        "MeanValue": np.mean(v_channel, where=mask),
        "StdHue": np.std(h_channel, where=mask),
        "StdSaturation": np.std(s_channel, where=mask),
        "StdValue": np.std(v_channel, where=mask),
    }


def _calculate_blur(img):
    """Calculate blur metric (Laplacian variance) for an object image."""
    if img is None or img.size == 0:
        return 0.0
    if len(img.shape) < 2:
        return 0.0
    if len(img.shape) == 3:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    else:
        gray = img
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def _augment_slice(dim_slice, max_dims, size=10):
    """Expand a bounding slice by `size` pixels in each direction."""
    dim_slice = list(dim_slice)
    for i in range(2):
        if dim_slice[i].start < size:
            dim_slice[i] = slice(0, dim_slice[i].stop)
        else:
            dim_slice[i] = slice(dim_slice[i].start - size, dim_slice[i].stop)
    for i in range(2):
        if dim_slice[i].stop + size >= max_dims[i]:
            dim_slice[i] = slice(dim_slice[i].start, max_dims[i])
        else:
            dim_slice[i] = slice(dim_slice[i].start, dim_slice[i].stop + size)
    return tuple(dim_slice)


def _write_tsv_header(tsv_path):
    """Write EcoTaxa TSV header if the file does not exist yet."""
    if os.path.exists(tsv_path):
        return
    with open(tsv_path, "w") as f:
        f.write("\t".join(ECOTAXA_COLUMNS) + "\n")
        types = ["[t]"] * len(ECOTAXA_COLUMNS)
        f.write("\t".join(types) + "\n")


def _append_tsv_row(tsv_path, row_data):
    """Append a single row to the EcoTaxa TSV file."""
    with open(tsv_path, "a") as f:
        values = []
        for col in ECOTAXA_COLUMNS:
            val = row_data.get(col, "")
            if isinstance(val, float):
                values.append(f"{val:.6f}")
            else:
                values.append(str(val))
        f.write("\t".join(values) + "\n")


def segment_frame(
    image_path: str,
    objects_dir: str,
    flat_ref_path: str | None,
    metadata: dict,
    frame_index: int,
    object_id_offset: int,
    min_esd_um: float = 20.0,
) -> dict:
    """Segment a single frame and save object crops + TSV rows.

    This is the top-level entry point for ProcessPoolExecutor workers.
    It is a pure function with no unpicklable state.

    Args:
        image_path: Path to the captured frame (JPEG).
        objects_dir: Directory to save object crops and TSV file.
        flat_ref_path: Path to .flatfield_ref.npy, or None to skip flat field.
        metadata: Acquisition metadata dict (must contain sample_id, acq_id, etc.).
        frame_index: 0-based index of this frame in the acquisition.
        object_id_offset: Starting object ID counter for this frame (ensures global uniqueness).
        min_esd_um: Minimum equivalent spherical diameter in microns.

    Returns:
        dict with keys:
            - objects_found (int): number of objects detected
            - objects_saved (int): number of objects saved (after size filter)
            - processing_time_ms (int): wall-clock time in ms
            - next_object_id_offset (int): updated offset for the next frame
            - error (str or None): error message if something went wrong
    """
    start_time = time.monotonic()
    try:
        # Read image
        img = cv2.imread(image_path)
        if img is None:
            return {"objects_found": 0, "objects_saved": 0, "processing_time_ms": 0,
                    "next_object_id_offset": object_id_offset, "error": f"Could not read {image_path}"}

        # Apply flat field correction
        if flat_ref_path and os.path.exists(flat_ref_path):
            flat_ref = np.load(flat_ref_path)
            img = _apply_flat_field(img, flat_ref)

        # Convert to grayscale and create mask
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        mask = _create_mask(gray)

        # Label connected components and get regionprops
        labels, nlabels = skimage.measure.label(mask, return_num=True)
        regionprops = skimage.measure.regionprops(labels)

        # Convert min ESD threshold from um to pixels
        pixel_size = metadata.get("process_pixel", None)
        try:
            pixel_size_um = float(pixel_size) if pixel_size is not None else None
        except (ValueError, TypeError):
            pixel_size_um = None

        if pixel_size_um and pixel_size_um > 0:
            min_esd_pixels = min_esd_um / pixel_size_um
        else:
            min_esd_pixels = min_esd_um

        # Filter by size
        regionprops_filtered = [
            r for r in regionprops if r.equivalent_diameter_area >= min_esd_pixels
        ]

        # Ensure output directory exists
        Path(objects_dir).mkdir(parents=True, exist_ok=True)

        # Setup TSV file
        base_name = os.path.splitext(os.path.basename(image_path))[0]
        folder_name = os.path.basename(objects_dir)
        tsv_path = os.path.join(objects_dir, f"ecotaxa_{folder_name}.tsv")
        _write_tsv_header(tsv_path)

        # Parse date/time from filename
        img_date = metadata.get("object_date", "")
        img_time = "00:00:00"
        if "_" in base_name:
            parts = base_name.split("_")
            if len(parts) > 1:
                img_time = parts[1].replace("-", ":")[:8]

        sample_id = str(metadata.get("sample_id", ""))
        acq_id = str(metadata.get("acq_id", ""))
        project = str(metadata.get("sample_project", ""))

        objects_saved = 0
        current_offset = object_id_offset

        for region in regionprops_filtered:
            region.label = current_offset
            current_offset += 1

            # Extract object image (with 10px padding)
            obj_image = img[region.slice]
            colors = _get_color_info(obj_image, region.filled_image)
            morph = _extract_metadata_from_regionprop(region, pixel_size_um=pixel_size_um)
            blur = _calculate_blur(obj_image)

            # Save expanded crop
            expanded = _augment_slice(region.slice, labels.shape, 10)
            crop = img[expanded]
            object_id = f"{base_name}_{objects_saved}"
            crop_filename = f"{object_id}.jpg"
            crop_path = os.path.join(objects_dir, crop_filename)
            cv2.imwrite(crop_path, crop)

            # Write TSV row
            row = {
                "object_id": f"{sample_id}_{acq_id}_{region.label}",
                "object_date": img_date,
                "object_time": img_time,
                "object_lat": 0,
                "object_lon": 0,
                "object_depth_min": 0,
                "object_depth_max": 0,
                "object_label": "",
                "object_bx": morph["bx"],
                "object_by": morph["by"],
                "object_x": morph["x"],
                "object_y": morph["y"],
                "object_width": morph["width"],
                "object_height": morph["height"],
                "object_area": morph["area"],
                "object_area_exc": morph["area_exc"],
                "object_%area": morph["%area"],
                "object_perim.": morph["perim."],
                "object_major": morph["major"],
                "object_minor": morph["minor"],
                "object_circ.": morph["circ."],
                "object_circex": morph["circex"],
                "object_elongation": morph["elongation"],
                "object_solidity": morph["solidity"],
                "object_eccentricity": morph["eccentricity"],
                "object_equivalent_diameter": morph["equivalent_diameter"],
                "object_convex_area": morph["convex_area"],
                "object_bounding_box_area": morph["bounding_box_area"],
                "object_angle": morph["angle"],
                "object_perimareaexc": morph["perimareaexc"],
                "object_perimmajor": morph["perimmajor"],
                "object_euler_number": morph["euler_number"],
                "object_extent": morph["extent"],
                "object_local_centroid_col": morph["local_centroid_col"],
                "object_local_centroid_row": morph["local_centroid_row"],
                "object_MeanHue": colors["MeanHue"],
                "object_MeanSaturation": colors["MeanSaturation"],
                "object_MeanValue": colors["MeanValue"],
                "object_StdHue": colors["StdHue"],
                "object_StdSaturation": colors["StdSaturation"],
                "object_StdValue": colors["StdValue"],
                "object_blur_laplacian": blur,
                "sample_id": sample_id,
                "sample_project": project,
                "acq_id": acq_id,
                "process_pixel": pixel_size_um if pixel_size_um else "",
                "img_file_name": crop_filename,
            }
            _append_tsv_row(tsv_path, row)
            objects_saved += 1

        # Save debug visualization
        vis_img = img.copy()
        for region in regionprops_filtered:
            cv2.rectangle(
                vis_img,
                pt1=(region.bbox[1], region.bbox[0]),
                pt2=(region.bbox[3], region.bbox[2]),
                color=(0, 255, 0),
                thickness=2,
            )
        debug_path = image_path.replace(".jpg", "_debug.jpg")
        cv2.imwrite(debug_path, vis_img)

        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        return {
            "objects_found": nlabels,
            "objects_saved": objects_saved,
            "processing_time_ms": elapsed_ms,
            "next_object_id_offset": current_offset,
            "error": None,
        }

    except Exception as e:
        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        logger.error(f"Live segmentation failed for {image_path}: {e}")
        return {
            "objects_found": 0,
            "objects_saved": 0,
            "processing_time_ms": elapsed_ms,
            "next_object_id_offset": object_id_offset,
            "error": str(e),
        }
