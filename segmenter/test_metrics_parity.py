"""Parity check: the serial and parallel segmentation paths must agree.

Run on the device:  cd /opt/PlanktoScope/segmenter && uv run test_metrics_parity.py

This guards the specific regression that motivated planktoscope.segmenter.metrics:
worker.py used to carry its own copies of the per-object metric functions, which
silently drifted from the serial ones (missing bw/bh, missing contour, blur
computed without the object mask). A clean git merge could not detect that.
"""

import json
import sys

import numpy as np
import skimage.measure

import planktoscope.segmenter
import planktoscope.segmenter.metrics as metrics
import planktoscope.segmenter.worker as worker

failures = []


def check(label, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {label}{(' — ' + detail) if detail else ''}")
    if not cond:
        failures.append(label)


print("1. Both paths resolve the metric functions to the same objects")
# Structural guarantee: neither module may hold a private copy.
check(
    "worker uses shared metrics module",
    worker.planktoscope.segmenter.metrics is metrics,
)
check(
    "serial path uses shared metrics module",
    planktoscope.segmenter.planktoscope.segmenter.metrics is metrics,
)
# The exact names worker.py used to define itself, before de-duplication.
for name in ("_extract_metadata_from_regionprop", "_get_color_info"):
    check(f"worker no longer defines its own {name}", not hasattr(worker, name))

print("\n2. Metrics on a synthetic object")
# A filled disc with an interior hole, offset inside a larger frame.
frame = np.zeros((200, 240), dtype=np.uint8)
yy, xx = np.ogrid[:200, :240]
disc = (yy - 90) ** 2 + (xx - 110) ** 2 <= 34**2
hole = (yy - 90) ** 2 + (xx - 110) ** 2 <= 12**2
frame[disc] = 1
frame[hole] = 0

labels = skimage.measure.label(frame)
props = skimage.measure.regionprops(labels)
check("one region found", len(props) == 1, f"got {len(props)}")
prop = props[0]

md = metrics.extract_metadata_from_regionprop(prop, pixel_size_um=2.0)

# The fields that went missing in the drifted parallel copy.
check("bw present", "bw" in md, f"bw={md.get('bw')}")
check("bh present", "bh" in md, f"bh={md.get('bh')}")
check(
    "bw/bh are pixels, not microns",
    md["bw"] == prop.bbox[3] - prop.bbox[1] and md["bh"] == prop.bbox[2] - prop.bbox[0],
    f"bw={md['bw']} bh={md['bh']}",
)
check(
    "width/height are scaled by pixel size",
    abs(md["width"] - md["bw"] * 2.0) < 1e-9,
    f"width={md['width']} bw*2={md['bw'] * 2.0}",
)
check("hole detected in %area", md["%area"] > 0, f"%area={md['%area']:.4f}")

print("\n3. Contour polygon")
poly = metrics.extract_contour_polygon(prop)
check("contour non-empty", len(poly) > 0, f"{len(poly)} points")
check("contour is point-capped", len(poly) <= 60, f"{len(poly)} points")
encoded = json.dumps(poly)
check("contour round-trips as JSON", json.loads(encoded) == poly)
check(
    "contour in full-frame coords",
    all(0 <= x < 240 and 0 <= y < 200 for x, y in poly),
)
# The polygon must actually trace the disc, not the bounding box.
cx = sum(p[0] for p in poly) / len(poly)
cy = sum(p[1] for p in poly) / len(poly)
check("contour centred on the object", abs(cx - 110) < 6 and abs(cy - 90) < 6,
      f"centroid=({cx:.1f}, {cy:.1f})")

print("\n4. Blur is masked")
rng = np.random.default_rng(0)
obj = rng.integers(0, 255, size=prop.image.shape + (3,), dtype=np.uint8)
masked = metrics.compute_blur(obj, prop)
import planktoscope.segmenter.operations as ops
unmasked = ops.calculate_blur(obj)
check("compute_blur returns a value", masked is not None, f"{masked}")
check(
    "compute_blur differs from the unmasked score",
    masked is not None and unmasked is not None and abs(masked - unmasked) > 1e-12,
    f"masked={masked} unmasked={unmasked}",
)

print("\n" + ("FAILED: " + ", ".join(failures) if failures else "ALL PARITY CHECKS PASSED"))
sys.exit(1 if failures else 0)
