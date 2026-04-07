#!/usr/bin/env python3
"""Verification tests for the pixel size management fix.

Run with: python3 test_pixel_fix.py

No dependencies required beyond the standard library — this tests the logic
directly without importing project modules (which need RPi hardware libs).
"""

import json
import sys

PASS = 0
FAIL = 0


def check(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}  — {detail}")


# =============================================================================
# Test 1: Imager metadata injection logic
# =============================================================================
print("\n=== Test 1: Imager process_pixel fallback ===")


def build_metadata(user_metadata):
    """Simulates the metadata construction in controller/imager/main.py:170-187

    Node-RED resolves the correct value from the per-preset calibration matrix
    and sends it as process_pixel. Python just uses it.
    """
    metadata = {
        **user_metadata,
        "acq_local_datetime": "2026-03-31T12:00:00",
        "acq_camera_resolution": "4056x3040",
        "acq_camera_iso": 150,
        "acq_camera_shutter_speed": 125,
        "acq_uuid": "test-uuid",
        "sample_uuid": "test-sample-uuid",
    }
    # Resolve pixel size — Node-RED sends the already-resolved process_pixel.
    pixel_size = metadata.get("process_pixel")
    if pixel_size is not None:
        metadata["process_pixel"] = float(pixel_size)
    return metadata


# Case 1a: Node-RED sends process_pixel → used directly
user_config_with_pixel = {"acq_celltype": 300, "process_pixel": 0.75}
meta = build_metadata(user_config_with_pixel)
check(
    "process_pixel from Node-RED used directly",
    meta.get("process_pixel") == 0.75,
    f"got {meta.get('process_pixel')}",
)

# Case 1b: process_pixel absent → stays absent (warning logged in real code)
user_config_bare = {"acq_celltype": 300}
meta = build_metadata(user_config_bare)
check(
    "No process_pixel → remains absent (graceful)",
    "process_pixel" not in meta,
    f"unexpectedly got {meta.get('process_pixel')}",
)

# =============================================================================
# Test 1b: Per-preset calibration matrix resolution
# =============================================================================
print("\n=== Test 1b: Per-preset calibration matrix ===")

# Simulate the calibration matrix that Node-RED manages
calibration_matrix = {
    "high":   {"factory": 0.53, "user_calibrated": None},
    "medium": {"factory": 0.75, "user_calibrated": None},
    "low":    {"factory": 1.34, "user_calibrated": None},
}


def resolve_pixel_size(matrix, preset):
    """Simulates Node-RED calibration matrix resolution."""
    entry = matrix[preset]
    if entry["user_calibrated"] is not None:
        return entry["user_calibrated"]
    return entry["factory"]


# Case: High magnification, no user calibration → factory default
pixel = resolve_pixel_size(calibration_matrix, "high")
high_mag_config = {"acq_celltype": 100, "process_pixel": pixel}
meta = build_metadata(high_mag_config)
check(
    "High mag (uncalibrated): process_pixel = 0.53 (factory)",
    meta["process_pixel"] == 0.53,
    f"got {meta.get('process_pixel')}",
)

# Case: Low magnification, no user calibration → factory default
pixel = resolve_pixel_size(calibration_matrix, "low")
low_mag_config = {"acq_celltype": 500, "process_pixel": pixel}
meta = build_metadata(low_mag_config)
check(
    "Low mag (uncalibrated): process_pixel = 1.34 (factory)",
    meta["process_pixel"] == 1.34,
    f"got {meta.get('process_pixel')}",
)

# Case: Medium magnification, no user calibration
pixel = resolve_pixel_size(calibration_matrix, "medium")
med_mag_config = {"acq_celltype": 300, "process_pixel": pixel}
meta = build_metadata(med_mag_config)
check(
    "Medium mag (uncalibrated): process_pixel = 0.75 (factory)",
    meta["process_pixel"] == 0.75,
    f"got {meta.get('process_pixel')}",
)

# Case: User calibrates high optics to 0.55
calibration_matrix["high"]["user_calibrated"] = 0.55
pixel = resolve_pixel_size(calibration_matrix, "high")
custom_high = {"acq_celltype": 100, "process_pixel": pixel}
meta = build_metadata(custom_high)
check(
    "High mag (calibrated): process_pixel = 0.55 (user calibration wins)",
    meta["process_pixel"] == 0.55,
    f"got {meta.get('process_pixel')}",
)

# Case: Switching to medium doesn't lose high calibration
pixel_med = resolve_pixel_size(calibration_matrix, "medium")
meta_med = build_metadata({"acq_celltype": 300, "process_pixel": pixel_med})
check(
    "Switch to medium: process_pixel = 0.75 (medium factory)",
    meta_med["process_pixel"] == 0.75,
    f"got {meta_med.get('process_pixel')}",
)
# Switch back to high — calibration still there
pixel_high_again = resolve_pixel_size(calibration_matrix, "high")
check(
    "Switch back to high: calibration 0.55 preserved",
    pixel_high_again == 0.55,
    f"got {pixel_high_again}",
)

# Case: User calibrates medium to 0.762
calibration_matrix["medium"]["user_calibrated"] = 0.762
pixel = resolve_pixel_size(calibration_matrix, "medium")
meta = build_metadata({"acq_celltype": 300, "process_pixel": pixel})
check(
    "Medium mag (calibrated): process_pixel = 0.762 (user calibration)",
    meta["process_pixel"] == 0.762,
    f"got {meta.get('process_pixel')}",
)

# Reset for later tests
calibration_matrix["high"]["user_calibrated"] = None
calibration_matrix["medium"]["user_calibrated"] = None

# =============================================================================
# Test 2: ESD filtering math
# =============================================================================
print("\n=== Test 2: Min ESD filtering threshold ===")


def compute_min_esd_pixels(process_min_ESD, process_pixel):
    """Simulates segmenter/__init__.py:440-462"""
    pixel_size = process_pixel
    try:
        pixel_size = float(pixel_size) if pixel_size is not None else None
    except (ValueError, TypeError):
        pixel_size = None
    if pixel_size and pixel_size > 0:
        return process_min_ESD / pixel_size
    else:
        return process_min_ESD  # legacy fallback


# With calibration: 20µm / 0.75 µm/px = 26.67 px
result = compute_min_esd_pixels(20, 0.75)
check(
    "20µm @ 0.75µm/px → 26.67px threshold",
    abs(result - 26.667) < 0.01,
    f"got {result:.3f}",
)

# Verify this corresponds to 20µm physical size
effective_um = result * 0.75
check(
    "26.67px × 0.75µm/px = 20µm (round-trip)",
    abs(effective_um - 20.0) < 0.01,
    f"got {effective_um:.3f}",
)

# Without calibration (the old bug): threshold is 20 pixels = 15µm
result_no_cal = compute_min_esd_pixels(20, None)
effective_no_cal = result_no_cal * 0.75
check(
    "BUG CASE: without calibration, threshold is 20px = 15µm (not 20µm)",
    abs(effective_no_cal - 15.0) < 0.01,
    f"got {effective_no_cal:.3f}",
)

# =============================================================================
# Test 3: Measurement scaling
# =============================================================================
print("\n=== Test 3: Measurement unit scaling ===")


def extract_metadata_scaling(pixel_size_um):
    """Simulates the scaling logic in _extract_metadata_from_regionprop"""
    px = pixel_size_um if pixel_size_um and pixel_size_um > 0 else 1.0
    px2 = px * px
    return px, px2


# With calibration
px, px2 = extract_metadata_scaling(0.75)
check("Linear scale factor = 0.75", px == 0.75)
check("Area scale factor = 0.5625", px2 == 0.5625)

# Without calibration (old bug)
px_none, px2_none = extract_metadata_scaling(None)
check("Without calibration: linear scale = 1.0 (pixels)", px_none == 1.0)
check("Without calibration: area scale = 1.0 (pixels²)", px2_none == 1.0)

# Example: object with 1000 pixel area
area_pixels = 1000
area_um2 = area_pixels * px2
check(
    "1000px² area → 562.5µm² with calibration",
    area_um2 == 562.5,
    f"got {area_um2}",
)

# Example: equivalent diameter
import math

eq_diam_pixels = math.sqrt(4 * area_pixels / math.pi)  # ~35.68 px
eq_diam_um = eq_diam_pixels * px
check(
    "ESD of 1000px² object → ~26.76µm (not 35.68µm in pixels)",
    abs(eq_diam_um - 26.76) < 0.01,
    f"got {eq_diam_um:.2f}",
)

# =============================================================================
# Test 4: Metadata filter preserves process_pixel
# =============================================================================
print("\n=== Test 4: Metadata prefix filter ===")

test_metadata = {
    "acq_celltype": 300,
    "sample_project": "Test",
    "object_date": "2026-03-31",
    "process_pixel": 0.75,
    "process_pixel_applied": True,
    "calibration_date": "2026-01-01",
    "nb_frame": 100,  # should be filtered OUT (no matching prefix)
    "sleep_before": 0.5,  # should be filtered OUT
}

# Simulates segmenter/__init__.py:806-812
filtered = dict(
    filter(
        lambda item: item[0].startswith(
            ("acq", "sample", "object", "process", "calibration")
        ),
        test_metadata.items(),
    )
)

check(
    "process_pixel survives prefix filter",
    "process_pixel" in filtered and filtered["process_pixel"] == 0.75,
)
check(
    "process_pixel_applied survives prefix filter",
    "process_pixel_applied" in filtered,
)
check("nb_frame filtered out", "nb_frame" not in filtered)
check("sleep_before filtered out", "sleep_before" not in filtered)
check("acq_celltype kept", "acq_celltype" in filtered)

# =============================================================================
# Test 5: EcoTaxa naming format
# =============================================================================
print("\n=== Test 5: EcoTaxa naming format ===")


def make_archive_name(project, acquisition):
    """Simulates segmenter/__init__.py:855-858"""
    return f"Ecotaxa_{project}_{acquisition}.zip"


def make_tsv_name(sample_project, acq_id):
    """Simulates ecotaxa.py:272-275"""
    project = (sample_project or "unknown_project").replace(" ", "_")
    acquisition_id = (acq_id or "unknown_acq").replace(" ", "_")
    return f"Ecotaxa_{project}_{acquisition_id}.tsv"


check(
    "Archive: Ecotaxa_My_Project_acq_001.zip",
    make_archive_name("My_Project", "acq_001") == "Ecotaxa_My_Project_acq_001.zip",
)
check(
    "TSV: spaces replaced with underscores",
    make_tsv_name("Tara Sud 2021", "acq 001") == "Ecotaxa_Tara_Sud_2021_acq_001.tsv",
)
check(
    "TSV: fallback for missing project",
    make_tsv_name(None, "acq_001") == "Ecotaxa_unknown_project_acq_001.tsv",
)

# =============================================================================
# Test 6: Full pipeline simulation — all three magnifications
# =============================================================================
print("\n=== Test 6: Full pipeline (end-to-end simulation) ===")

# Magnification presets (mirrors Node-RED acquisition page)
MAG_PRESETS = {
    "high":   {"pixel_size": 0.53, "thickness": 100},
    "medium": {"pixel_size": 0.75, "thickness": 300},
    "low":    {"pixel_size": 1.34, "thickness": 500},
}


def run_e2e(mag_name, preset):
    """Simulate full pipeline for a magnification preset."""
    pixel = preset["pixel_size"]
    thickness = preset["thickness"]

    # Node-RED resolves from calibration matrix and sends process_pixel
    user_mqtt_config = {
        "sample_project": "Atlantic Survey 2026",
        "sample_id": "sample_001",
        "acq_id": "acq_001",
        "acq_celltype": thickness,
        "acq_minimum_mesh": 20,
        "object_date": "2026-03-31",
        "process_pixel": pixel,
        "acq_magnification": mag_name,
    }

    # Step 1: Imager resolves pixel size
    metadata = build_metadata(user_mqtt_config)
    check(
        f"E2E {mag_name}: process_pixel = {pixel}",
        metadata["process_pixel"] == pixel,
        f"got {metadata.get('process_pixel')}",
    )

    # Step 2: Round-trip through JSON (simulates metadata.json save/load)
    loaded = json.loads(json.dumps(metadata))

    # Step 3: Segmenter prefix filter
    filtered = dict(
        filter(
            lambda item: item[0].startswith(
                ("acq", "sample", "object", "process", "calibration")
            ),
            loaded.items(),
        )
    )
    check(
        f"E2E {mag_name}: process_pixel survives filter",
        filtered.get("process_pixel") == pixel,
    )

    # Step 4: ESD filtering — should always resolve to 20µm
    min_esd_px = compute_min_esd_pixels(20, filtered["process_pixel"])
    effective_um = min_esd_px * pixel
    check(
        f"E2E {mag_name}: min ESD = {min_esd_px:.1f}px → {effective_um:.1f}µm",
        abs(effective_um - 20.0) < 0.01,
        f"got {effective_um:.2f}µm",
    )

    # Step 5: Measurement scaling
    px_scale, px2_scale = extract_metadata_scaling(filtered["process_pixel"])
    check(
        f"E2E {mag_name}: linear scale = {pixel}",
        px_scale == pixel,
    )


for mag_name, preset in MAG_PRESETS.items():
    run_e2e(mag_name, preset)

# Also test the case where process_pixel is missing (should not happen with current Node-RED)
print("\n=== Test 6b: Missing process_pixel (graceful) ===")
legacy_config = {
    "sample_project": "Legacy Project",
    "sample_id": "s1",
    "acq_id": "a1",
    "acq_celltype": 300,
    "object_date": "2026-03-31",
}
meta = build_metadata(legacy_config)
check("Missing process_pixel: not in metadata", "process_pixel" not in meta)

# =============================================================================
# Summary
# =============================================================================
print(f"\n{'='*50}")
print(f"Results: {PASS} passed, {FAIL} failed")
if FAIL > 0:
    print("SOME TESTS FAILED!")
    sys.exit(1)
else:
    print("ALL TESTS PASSED")
    sys.exit(0)
