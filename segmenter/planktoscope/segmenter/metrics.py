"""Per-object metrics shared by the serial and parallel segmentation paths.

Both `planktoscope.segmenter` (serial, in-process) and
`planktoscope.segmenter.worker` (parallel, multiprocessing pool) must emit
byte-identical per-object metadata — an acquisition segmented either way has
to produce the same EcoTaxa columns and the same values.

These functions previously existed as two independent copies, which silently
drifted: the parallel copy missed the `bw`/`bh` bounding-box fields, omitted
the contour polygon entirely, and computed the blur score without the object
mask. Those bugs merged cleanly and produced no error — just different numbers
depending on which path ran. Keep this module the single source of truth; do
not re-inline these into either caller.
"""

import cv2
import numpy as np

import planktoscope.segmenter.operations


def compute_blur(obj_image, prop):
    """Focus measure for one object, masked to the object itself.

    The mask matters: `calculate_blur` is a Laplacian-energy / gradient-energy
    ratio over the edge band, and without the mask, background inside the
    bounding box dilutes the score. Both paths must pass it.
    """
    return planktoscope.segmenter.operations.calculate_blur(
        obj_image, mask=prop.filled_image
    )


def extract_contour_polygon(prop, max_points=60):
    """Extract the object's outer contour as a full-frame [[x, y], ...] polygon.

    Uses cv2.findContours on the region's binary mask with RETR_EXTERNAL
    (outer ring only, no holes) and CHAIN_APPROX_TC89_KCOS (Teh–Chin
    simplification). The `offset` arg shifts points into the full-frame
    coordinate system so downstream consumers (dashboard, audit UI) can
    plot them directly on the flowcell image without re-registering.

    Payload is further simplified via approxPolyDP and, if still over
    `max_points`, uniformly subsampled. Typical output: 20–50 points per
    object, ~0.2–0.5 KB serialised.

    Returns a list of [int, int] pairs in (x=col, y=row) order. Empty
    list if no contour could be traced.
    """
    try:
        contours, _ = cv2.findContours(
            np.uint8(prop.image),
            mode=cv2.RETR_EXTERNAL,
            method=cv2.CHAIN_APPROX_TC89_KCOS,
            offset=(int(prop.bbox[1]), int(prop.bbox[0])),
        )
    except cv2.error:
        return []
    if not contours:
        return []
    # Pick the largest ring (there should usually only be one with RETR_EXTERNAL)
    poly = max(contours, key=cv2.contourArea)
    # Ramer–Douglas–Peucker simplification; epsilon scales with perimeter
    # so small and large objects both land in a similar point budget.
    epsilon = max(0.8, 0.004 * cv2.arcLength(poly, True))
    simplified = cv2.approxPolyDP(poly, epsilon, True)
    pts = simplified.reshape(-1, 2)
    if len(pts) > max_points:
        step = max(1, len(pts) // max_points)
        pts = pts[::step][:max_points]
    return [[int(p[0]), int(p[1])] for p in pts]


def get_color_info(bgr_img, mask):
    # bgr_mean, bgr_stddev = cv2.meanStdDev(bgr_img, mask=mask)
    # (b_channel, g_channel, r_channel) = cv2.split(bgr_img)
    # quartiles = [0, 0.05, 0.25, 0.50, 0.75, 0.95, 1]
    # b_quartiles = np.quantile(b_channel, quartiles)
    # g_quartiles = np.quantile(g_channel, quartiles)
    # r_quartiles = np.quantile(r_channel, quartiles)
    hsv_img = cv2.cvtColor(bgr_img, cv2.COLOR_BGR2HSV)
    (h_channel, s_channel, v_channel) = cv2.split(hsv_img)
    # hsv_mean, hsv_stddev = cv2.meanStdDev(hsv_img, mask=mask)
    h_mean = np.mean(h_channel, where=mask)
    s_mean = np.mean(s_channel, where=mask)
    v_mean = np.mean(v_channel, where=mask)
    h_stddev = np.std(h_channel, where=mask)
    s_stddev = np.std(s_channel, where=mask)
    v_stddev = np.std(v_channel, where=mask)
    # TODO #103 Add skewness and kurtosis calculation (with scipy) here
    # using https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.skew.html#scipy.stats.skew
    # and https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.kurtosis.html#scipy.stats.kurtosis
    # h_quartiles = np.quantile(h_channel, quartiles)
    # s_quartiles = np.quantile(s_channel, quartiles)
    # v_quartiles = np.quantile(v_channel, quartiles)
    return {
        # "object_MeanRedLevel": bgr_mean[2][0],
        # "object_MeanGreenLevel": bgr_mean[1][0],
        # "object_MeanBlueLevel": bgr_mean[0][0],
        # "object_StdRedLevel": bgr_stddev[2][0],
        # "object_StdGreenLevel": bgr_stddev[1][0],
        # "object_StdBlueLevel": bgr_stddev[0][0],
        # "object_minRedLevel": r_quartiles[0],
        # "object_Q05RedLevel": r_quartiles[1],
        # "object_Q25RedLevel": r_quartiles[2],
        # "object_Q50RedLevel": r_quartiles[3],
        # "object_Q75RedLevel": r_quartiles[4],
        # "object_Q95RedLevel": r_quartiles[5],
        # "object_maxRedLevel": r_quartiles[6],
        # "object_minGreenLevel": g_quartiles[0],
        # "object_Q05GreenLevel": g_quartiles[1],
        # "object_Q25GreenLevel": g_quartiles[2],
        # "object_Q50GreenLevel": g_quartiles[3],
        # "object_Q75GreenLevel": g_quartiles[4],
        # "object_Q95GreenLevel": g_quartiles[5],
        # "object_maxGreenLevel": g_quartiles[6],
        # "object_minBlueLevel": b_quartiles[0],
        # "object_Q05BlueLevel": b_quartiles[1],
        # "object_Q25BlueLevel": b_quartiles[2],
        # "object_Q50BlueLevel": b_quartiles[3],
        # "object_Q75BlueLevel": b_quartiles[4],
        # "object_Q95BlueLevel": b_quartiles[5],
        # "object_maxBlueLevel": b_quartiles[6],
        "MeanHue": h_mean,
        "MeanSaturation": s_mean,
        "MeanValue": v_mean,
        "StdHue": h_stddev,
        "StdSaturation": s_stddev,
        "StdValue": v_stddev,
        # "object_minHue": h_quartiles[0],
        # "object_Q05Hue": h_quartiles[1],
        # "object_Q25Hue": h_quartiles[2],
        # "object_Q50Hue": h_quartiles[3],
        # "object_Q75Hue": h_quartiles[4],
        # "object_Q95Hue": h_quartiles[5],
        # "object_maxHue": h_quartiles[6],
        # "object_minSaturation": s_quartiles[0],
        # "object_Q05Saturation": s_quartiles[1],
        # "object_Q25Saturation": s_quartiles[2],
        # "object_Q50Saturation": s_quartiles[3],
        # "object_Q75Saturation": s_quartiles[4],
        # "object_Q95Saturation": s_quartiles[5],
        # "object_maxSaturation": s_quartiles[6],
        # "object_minValue": v_quartiles[0],
        # "object_Q05Value": v_quartiles[1],
        # "object_Q25Value": v_quartiles[2],
        # "object_Q50Value": v_quartiles[3],
        # "object_Q75Value": v_quartiles[4],
        # "object_Q95Value": v_quartiles[5],
        # "object_maxValue": v_quartiles[6],
    }


def extract_metadata_from_regionprop(prop, pixel_size_um=None):
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
        # X coordinates of the top left point of the smallest rectangle enclosing the object (pixels)
        "bx": prop.bbox[1],
        # Y coordinates of the top left point of the smallest rectangle enclosing the object (pixels)
        "by": prop.bbox[0],
        # Width of the bounding box (pixels). Companion to bx/by/x/y for
        # consumers that draw in pixel space (e.g. the audit visualizer);
        # `width` above is in µm when calibrated for EcoTaxa compatibility.
        "bw": prop.bbox[3] - prop.bbox[1],
        # Height of the bounding box (pixels). See `bw` above.
        "bh": prop.bbox[2] - prop.bbox[0],
        # circularity : (4∗π ∗Area)/Perim^2 — dimensionless ratio, unaffected by scaling
        "circ.": (4 * np.pi * prop.filled_area) / prop.perimeter**2,
        # Surface area of the object excluding holes (µm² if calibrated)
        "area_exc": prop.area * px2,
        # Surface area of the object (µm² if calibrated)
        "area": prop.filled_area * px2,
        # Percentage of object’s surface area that is comprised of holes — dimensionless
        "%area": 1 - (prop.area / prop.filled_area),
        # Primary axis of the best fitting ellipse for the object (µm if calibrated)
        "major": prop.major_axis_length * px,
        # Secondary axis of the best fitting ellipse for the object (µm if calibrated)
        "minor": prop.minor_axis_length * px,
        # Y position of the center of gravity of the object (pixels)
        "y": prop.centroid[0],
        # X position of the center of gravity of the object (pixels)
        "x": prop.centroid[1],
        # The area of the smallest convex polygon enclosing the object (µm² if calibrated)
        "convex_area": prop.convex_area * px2,
        # The length of the outside boundary of the object (µm if calibrated)
        "perim.": prop.perimeter * px,
        # major/minor — dimensionless ratio
        "elongation": np.divide(prop.major_axis_length, prop.minor_axis_length),
        # perim/area_exc — units: 1/µm if calibrated (scales as 1/px)
        "perimareaexc": prop.perimeter / prop.area * (1.0 / px),
        # perim/major — dimensionless ratio
        "perimmajor": prop.perimeter / prop.major_axis_length,
        # (4 ∗ π ∗ Area_exc)/perim^2 — dimensionless ratio
        "circex": np.divide(4 * np.pi * prop.area, prop.perimeter**2),
        # Angle between the primary axis and a line parallel to the x-axis of the image
        "angle": prop.orientation / np.pi * 180 + 90,
        # Bounding box area (µm² if calibrated)
        "bounding_box_area": prop.bbox_area * px2,
        "eccentricity": prop.eccentricity,
        # Equivalent spherical diameter (µm if calibrated)
        "equivalent_diameter": prop.equivalent_diameter * px,
        "euler_number": prop.euler_number,
        # extent — dimensionless ratio (area / bounding_box_area)
        "extent": prop.extent,
        "local_centroid_col": prop.local_centroid[1],
        "local_centroid_row": prop.local_centroid[0],
        # solidity — dimensionless ratio (area / convex_area)
        "solidity": prop.solidity,
    }
