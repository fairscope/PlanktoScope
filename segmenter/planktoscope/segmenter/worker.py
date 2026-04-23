"""Top-level worker function for parallel image segmentation.

All functions in this module are module-level (picklable) so they can be used
with ProcessPoolExecutor. Workers do not hold MQTT connections — the parent
process publishes progress updates based on returned results.
"""

import multiprocessing.shared_memory
import os
import time

import cv2
import numpy as np
import PIL.Image
import skimage.exposure
import skimage.measure
from loguru import logger

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
        image = skimage.exposure.rescale_intensity(image, in_range=(0, 1.04), out_range="uint8")

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
        planktoscope.segmenter.streamer.write_image_objects(metadata_dir, image_name, objects)

        duration = time.monotonic() - start
        logger.info(
            f"Worker {os.getpid()}: {image_name} done — {object_count} objects in {duration:.1f}s"
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
            PIL.Image.fromarray(mask).save(os.path.join(debug_path, f"mask_{i}_{name}.jpg"))

    logger.success("Mask created")
    return mask


def _get_color_info(bgr_img, mask) -> dict:
    """Compute HSV color statistics for an object region.

    Args:
        bgr_img: BGR image of the object region
        mask: Boolean mask of the object within the region

    Returns:
        dict with MeanHue, StdHue, MeanSaturation, StdSaturation, MeanValue, StdValue
    """
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


def _extract_metadata_from_regionprop(prop, pixel_size_um=None) -> dict:
    """Extract morphological metadata from a scikit-image regionprop.

    Args:
        prop: scikit-image regionprop object
        pixel_size_um (float or None): pixel size in µm/pixel (process_pixel).
            If provided, linear measurements are in µm and area measurements in µm².
            If None, all measurements remain in pixel units.
    """
    # Scale factors: linear (µm/px) and area (µm²/px²)
    px = pixel_size_um if pixel_size_um and pixel_size_um > 0 else 1.0
    px2 = px * px

    return {
        "label": prop.label,
        # width of the smallest rectangle enclosing the object (µm if calibrated)
        "width": (prop.bbox[3] - prop.bbox[1]) * px,
        # height of the smallest rectangle enclosing the object (µm if calibrated)
        "height": (prop.bbox[2] - prop.bbox[0]) * px,
        # X coordinates of the top left point (pixels)
        "bx": prop.bbox[1],
        # Y coordinates of the top left point (pixels)
        "by": prop.bbox[0],
        # circularity — dimensionless ratio
        "circ.": (4 * np.pi * prop.filled_area) / prop.perimeter**2,
        # Surface area excluding holes (µm² if calibrated)
        "area_exc": prop.area * px2,
        # Surface area (µm² if calibrated)
        "area": prop.filled_area * px2,
        # Percentage of holes — dimensionless
        "%area": 1 - (prop.area / prop.filled_area),
        # Primary axis (µm if calibrated)
        "major": prop.major_axis_length * px,
        # Secondary axis (µm if calibrated)
        "minor": prop.minor_axis_length * px,
        # Y center of gravity (pixels)
        "y": prop.centroid[0],
        # X center of gravity (pixels)
        "x": prop.centroid[1],
        # Convex area (µm² if calibrated)
        "convex_area": prop.convex_area * px2,
        # Perimeter (µm if calibrated)
        "perim.": prop.perimeter * px,
        # major/minor — dimensionless
        "elongation": np.divide(prop.major_axis_length, prop.minor_axis_length),
        # perim/area_exc — units: 1/µm if calibrated
        "perimareaexc": prop.perimeter / prop.area * (1.0 / px),
        # perim/major — dimensionless
        "perimmajor": prop.perimeter / prop.major_axis_length,
        # (4∗π∗Area_exc)/perim² — dimensionless
        "circex": np.divide(4 * np.pi * prop.area, prop.perimeter**2),
        # Angle in degrees
        "angle": prop.orientation / np.pi * 180 + 90,
        # Bounding box area (µm² if calibrated)
        "bounding_box_area": prop.bbox_area * px2,
        "eccentricity": prop.eccentricity,
        # Equivalent diameter (µm if calibrated)
        "equivalent_diameter": prop.equivalent_diameter * px,
        "euler_number": prop.euler_number,
        # extent — dimensionless
        "extent": prop.extent,
        "local_centroid_col": prop.local_centroid[1],
        "local_centroid_row": prop.local_centroid[0],
        # solidity — dimensionless
        "solidity": prop.solidity,
    }


def _augment_slice(dim_slice, max_dims, size=10):
    """Expand a region slice by `size` pixels in each direction."""
    dim_slice = list(dim_slice)
    for i in range(2):
        if dim_slice[i].start < size:
            dim_slice[i] = slice(0, dim_slice[i].stop)
        else:
            dim_slice[i] = slice(dim_slice[i].start - size, dim_slice[i].stop)

    for i in range(2):
        if dim_slice[i].stop + size == max_dims[i]:
            dim_slice[i] = slice(dim_slice[i].start, max_dims[i])
        else:
            dim_slice[i] = slice(dim_slice[i].start, dim_slice[i].stop + size)

    return tuple(dim_slice)


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
        f"Min ESD filter: {min_ESD} µm = {min_esd_pixels:.1f} px (process_pixel={pixel_size})"
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

        # Extract metadata
        obj_image = img[region.slice]
        colors = _get_color_info(obj_image, region.filled_image)
        metadata = _extract_metadata_from_regionprop(region, pixel_size_um=pixel_size_um)

        # Blur metric
        metadata["blur_laplacian"] = planktoscope.segmenter.operations.calculate_blur(obj_image)

        # Threshold value (each worker has its own process-local global)
        threshold_value = planktoscope.segmenter.operations.get_last_threshold_value()
        if threshold_value is not None:
            metadata["threshold"] = threshold_value

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
