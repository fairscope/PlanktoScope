"""Top-level worker function for parallel image segmentation.

All functions in this module are module-level (picklable) so they can be used
with ProcessPoolExecutor. Workers do not hold MQTT connections — the parent
process publishes progress updates based on returned results.
"""

import json
import multiprocessing.shared_memory
import os
import time

import cv2
import numpy as np
import PIL.Image
import skimage.exposure
import skimage.measure
from loguru import logger

import planktoscope.segmenter.metrics
import planktoscope.segmenter.operations
import planktoscope.segmenter.streamer

# Per-worker cached flat reference (set by initializer)
_flat_shm = None
_flat_array = None


def worker_init(shm_name: str, flat_shape: tuple, flat_dtype: str) -> None:
    """Initializer for each worker process. Attaches to shared flat field."""
    global _flat_shm, _flat_array
    _flat_shm = multiprocessing.shared_memory.SharedMemory(name=shm_name, create=False)
    _flat_array = np.ndarray(flat_shape, dtype=flat_dtype, buffer=_flat_shm.buf)
    logger.debug(f"Worker {os.getpid()} attached to shared flat field '{shm_name}'")


def process_single_image(
    image_filepath: str,
    image_name: str,
    image_index: int,
    images_count: int,
    working_obj_path: str,
    working_debug_path: str,
    metadata_dir: str,
    save_debug_img: bool,
    process_min_ESD: float,
    global_metadata: dict,
) -> dict:
    """Process a single image: flat correction, masking, slicing, metadata write.

    Args:
        image_filepath: Full path to the source image
        image_name: Base name of the image (no extension)
        image_index: Index of this image in the acquisition
        images_count: Total number of images in the acquisition
        working_obj_path: Directory to save cropped object images
        working_debug_path: Directory for debug output (per-image subdirectory)
        metadata_dir: Directory for .jsonl intermediate metadata files
        save_debug_img: Whether to save debug images
        process_min_ESD: Minimum equivalent spherical diameter threshold (µm)
        global_metadata: Acquisition metadata dict (for process_pixel calibration etc.)

    Returns:
        dict with keys: image_name, image_index, object_count, duration
        On error: dict with keys: image_name, image_index, error
    """
    try:
        start = time.monotonic()

        # Create debug path if needed
        if save_debug_img:
            os.makedirs(working_debug_path, exist_ok=True)

        # 1. Open and apply flat
        image = cv2.imread(image_filepath)
        if image is None:
            raise FileNotFoundError(f"Could not read image: {image_filepath}")
        image = image / _flat_array
        image[0][0] = [0, 0, 0]
        image = skimage.exposure.rescale_intensity(
            image, in_range=(0, 1.04), out_range="uint8"
        )

        if save_debug_img:
            _save_image(image, os.path.join(working_debug_path, "cleaned_image.jpg"))

        # 2. Create mask (no remove_previous_mask in parallel mode)
        mask = _create_mask(image, working_debug_path, save_debug_img)

        # 3. Slice image and extract objects
        objects, object_count, unfiltered_count = _slice_image(
            image,
            image_name,
            mask,
            working_obj_path,
            working_debug_path,
            save_debug_img,
            process_min_ESD,
            global_metadata,
        )

        # 4. Write objects metadata to disk incrementally
        planktoscope.segmenter.streamer.write_image_objects(
            metadata_dir, image_name, objects
        )

        duration = time.monotonic() - start
        logger.info(
            f"Worker {os.getpid()}: {image_name} done — "
            f"{object_count} objects in {duration:.1f}s"
        )
        return {
            "image_name": image_name,
            "image_index": image_index,
            "object_count": object_count,
            "unfiltered_count": unfiltered_count,
            "duration": duration,
        }

    except Exception as e:
        logger.error(f"Worker {os.getpid()}: failed on {image_name}: {e}")
        return {
            "image_name": image_name,
            "image_index": image_index,
            "error": str(e),
        }


def _save_image(image, path: str) -> None:
    """Save a BGR image as JPEG."""
    PIL.Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB)).save(path)


def _save_mask(mask, path: str) -> None:
    """Save a binary mask as JPEG."""
    PIL.Image.fromarray(mask).save(path)


def _create_mask(img, debug_path: str, save_debug: bool):
    """Create segmentation mask without global state (no remove_previous_mask).

    In parallel mode, remove_previous_mask is always disabled (replaced by no_op)
    because it requires sequential image-to-image state.
    """
    logger.info("Starting the mask creation")

    pipeline = [
        ("simple_threshold", planktoscope.segmenter.operations.simple_threshold),
        ("no_op", planktoscope.segmenter.operations.no_op),
        ("erode", planktoscope.segmenter.operations.erode),
        ("dilate", planktoscope.segmenter.operations.dilate),
        ("close", planktoscope.segmenter.operations.close),
        ("erode2", planktoscope.segmenter.operations.erode2),
    ]

    mask = img
    for i, (name, func) in enumerate(pipeline):
        mask = func(mask)
        if save_debug and debug_path:
            PIL.Image.fromarray(mask).save(
                os.path.join(debug_path, f"mask_{i}_{name}.jpg")
            )

    logger.success("Mask created")
    return mask


def _slice_image(
    img,
    name: str,
    mask,
    obj_path: str,
    debug_path: str,
    save_debug: bool,
    min_ESD: float,
    global_metadata: dict,
) -> tuple[list[dict], int, int]:
    """Slice image into objects and extract metadata. No MQTT, no shared state.

    Args:
        img: BGR image array
        name: Base name of the source image
        mask: Binary segmentation mask
        obj_path: Directory to save cropped object images
        debug_path: Directory for debug output
        save_debug: Whether to save debug images
        min_ESD: Minimum equivalent spherical diameter threshold (µm)
        global_metadata: Acquisition metadata dict (for process_pixel)

    Returns:
        tuple: (objects_list, filtered_count, unfiltered_count)
    """
    labels, nlabels = skimage.measure.label(mask, return_num=True)
    regionprops = skimage.measure.regionprops(labels)

    # Convert min ESD threshold from µm to pixels for filtering
    pixel_size = global_metadata.get("process_pixel", None)
    try:
        pixel_size = float(pixel_size) if pixel_size is not None else None
    except (ValueError, TypeError):
        pixel_size = None
    if pixel_size and pixel_size > 0:
        min_esd_pixels = min_ESD / pixel_size
    else:
        min_esd_pixels = min_ESD
        logger.warning(
            f"No valid process_pixel calibration — using min ESD of {min_esd_pixels} as pixels"
        )
    logger.debug(
        f"Min ESD filter: {min_ESD} µm = {min_esd_pixels:.1f} px "
        f"(process_pixel={pixel_size})"
    )

    filtered = [r for r in regionprops if r.equivalent_diameter_area >= min_esd_pixels]
    object_number = len(filtered)
    logger.debug(f"Found {nlabels} labels, or {object_number} after size filtering")

    # Determine pixel_size_um for calibrated measurements
    pixel_size_um = None
    if pixel_size and pixel_size > 0:
        pixel_size_um = pixel_size

    objects = []
    for i, region in enumerate(filtered):
        region.label = i

        # Extract metadata. These come from planktoscope.segmenter.metrics so the
        # parallel path emits exactly the same fields and values as the serial
        # path in planktoscope.segmenter — do not re-inline them here.
        obj_image = img[region.slice]
        colors = planktoscope.segmenter.metrics.get_color_info(obj_image, region.filled_image)
        metadata = planktoscope.segmenter.metrics.extract_metadata_from_regionprop(
            region, pixel_size_um=pixel_size_um
        )

        # Blur metric (masked to the object, same as the serial path)
        metadata["blur_laplacian"] = planktoscope.segmenter.metrics.compute_blur(
            obj_image, region
        )

        # Threshold value (each worker has its own process-local global)
        threshold_value = planktoscope.segmenter.operations.get_last_threshold_value()
        if threshold_value is not None:
            metadata["threshold"] = threshold_value

        # External contour polygon in full-frame pixel coords, for the audit
        # visualizer. Compact JSON list of [x, y] points; consumers can parse
        # it with JSON.parse.
        contour_polygon = planktoscope.segmenter.metrics.extract_contour_polygon(region)
        if contour_polygon:
            metadata["contour"] = json.dumps(contour_polygon)

        # Save cropped object image with augmented slice
        obj_image_aug = img[_augment_slice(region.slice, labels.shape, 10)]
        object_id = f"{name}_{i}"
        _save_image(obj_image_aug, os.path.join(obj_path, f"{object_id}.jpg"))

        if save_debug and debug_path:
            _save_mask(
                region.filled_image,
                os.path.join(debug_path, f"obj_{i}_mask.jpg"),
            )

        objects.append({"name": object_id, "metadata": {**metadata, **colors}})

    # Debug tagged image
    if save_debug and debug_path:
        if object_number:
            tagged_image = img.copy()
            for region in filtered:
                tagged_image = cv2.drawMarker(
                    tagged_image,
                    (int(region.centroid[1]), int(region.centroid[0])),
                    (0, 0, 255),
                    cv2.MARKER_CROSS,
                )
                tagged_image = cv2.rectangle(
                    tagged_image,
                    pt1=region.bbox[-3:-5:-1],
                    pt2=region.bbox[-1:-3:-1],
                    color=(150, 0, 200),
                    thickness=1,
                )
                contours, _ = cv2.findContours(
                    np.uint8(region.image),
                    mode=cv2.RETR_TREE,
                    method=cv2.CHAIN_APPROX_NONE,
                )
                tagged_image = cv2.drawContours(
                    tagged_image,
                    contours,
                    -1,
                    (238, 130, 238),
                    thickness=1,
                    offset=(region.bbox[1], region.bbox[0]),
                )
            _save_image(tagged_image, os.path.join(debug_path, "tagged.jpg"))
        else:
            _save_image(img, os.path.join(debug_path, "tagged.jpg"))

    return objects, object_number, len(regionprops)
