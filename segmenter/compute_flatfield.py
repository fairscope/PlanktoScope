#!/usr/bin/env python3
"""Compute flat field reference from pre-acquisition frames.

Called by the imager controller as a subprocess using the segmenter venv.
Usage: python compute_flatfield.py <output_npy_path> <frame1.jpg> <frame2.jpg> ...
"""

import sys

import cv2
import numpy as np


def calculate_flatfield_reference(frame_paths: list[str], min_frames: int = 3):
    """Calculate flat field reference from multiple frames using median."""
    frames = []
    for path in frame_paths:
        img = cv2.imread(path)
        if img is not None:
            frames.append(img.astype(np.float32))

    if len(frames) < min_frames:
        return None

    stacked = np.stack(frames, axis=0)
    flat_ref = np.median(stacked, axis=0)

    # Normalize to mean intensity and clip to avoid division issues
    flat_ref = flat_ref / flat_ref.mean() * 128
    flat_ref = np.clip(flat_ref, 1, 255)

    return flat_ref.astype(np.float32)


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print(f"Usage: {sys.argv[0]} <output.npy> <frame1.jpg> <frame2.jpg> ...", file=sys.stderr)
        sys.exit(1)

    output_path = sys.argv[1]
    frame_paths = sys.argv[2:]

    flat_ref = calculate_flatfield_reference(frame_paths)
    if flat_ref is not None:
        np.save(output_path, flat_ref)
        print(f"Saved flat field reference to {output_path}")
    else:
        print("Failed to compute flat field reference", file=sys.stderr)
        sys.exit(1)
