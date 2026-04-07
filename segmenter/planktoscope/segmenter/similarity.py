"""UMAP-based similarity projection for segmented plankton objects.

After segmentation completes, this module projects the per-object feature
vectors into 2D using UMAP.  The result is written as a JSON file that
the frontend visualizer can fetch to render an interactive scatter plot.
"""

import json
import os
from typing import Any

import numpy as np
from loguru import logger
from sklearn.preprocessing import RobustScaler
import umap

# Keys to exclude from the feature matrix (identifiers, coordinates, non-numeric)
EXCLUDE_KEYS = frozenset({
    "label", "name", "bx", "by", "x", "y",
    "local_centroid_col", "local_centroid_row",
    "euler_number", "blur_laplacian", "threshold",
    "angle",
})

# Minimum number of objects needed for a meaningful projection
MIN_OBJECTS = 5


def compute_umap_projection(
    objects_list: list[dict[str, Any]],
    output_path: str,
    n_neighbors: int = 15,
    min_dist: float = 0.1,
) -> str | None:
    """Compute a UMAP 2D projection from per-object feature metadata.

    Args:
        objects_list: list of dicts, each with ``"name"`` and ``"metadata"`` keys
            as stored in ``__global_metadata["objects"]``.
        output_path: directory where ``umap_projection.json`` will be written.
        n_neighbors: UMAP locality parameter (5-50).
        min_dist: UMAP minimum distance between embedded points.

    Returns:
        Absolute path to the written JSON file, or *None* if too few objects.
    """
    n = len(objects_list)
    if n < MIN_OBJECTS:
        logger.warning(f"Only {n} objects — skipping UMAP projection (need >= {MIN_OBJECTS})")
        return None

    # Determine numeric feature columns from the first object
    first_meta = objects_list[0]["metadata"]
    feature_keys = sorted(
        k for k, v in first_meta.items()
        if isinstance(v, (int, float)) and k not in EXCLUDE_KEYS
    )
    m = len(feature_keys)
    logger.info(f"Building UMAP feature matrix: {n} objects x {m} features")

    # Build the feature matrix
    X = np.empty((n, m), dtype=np.float64)
    names: list[str] = []
    for i, obj in enumerate(objects_list):
        names.append(obj["name"])
        meta = obj["metadata"]
        for j, key in enumerate(feature_keys):
            val = meta.get(key, 0.0)
            X[i, j] = float(val) if val is not None else 0.0

    # Replace any NaN / Inf values (can occur from degenerate objects)
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

    # Normalize — RobustScaler handles outlier measurements better than StandardScaler
    scaler = RobustScaler()
    X_scaled = scaler.fit_transform(X)

    # UMAP projection to 2D
    effective_neighbors = min(n_neighbors, n - 1)
    reducer = umap.UMAP(
        n_neighbors=effective_neighbors,
        min_dist=min_dist,
        n_components=2,
        random_state=42,
    )
    embedding = reducer.fit_transform(X_scaled)
    logger.info("UMAP projection complete")

    # Build output JSON
    result: dict[str, Any] = {
        "feature_keys": feature_keys,
        "n_objects": n,
        "n_features": m,
        "objects": [],
    }
    for i, obj in enumerate(objects_list):
        meta = obj["metadata"]
        result["objects"].append({
            "name": names[i],
            "umap_x": float(embedding[i, 0]),
            "umap_y": float(embedding[i, 1]),
            # Key features for color-by in the visualizer
            "area": meta.get("area", 0),
            "equivalent_diameter": meta.get("equivalent_diameter", 0),
            "MeanHue": meta.get("MeanHue", 0),
            "MeanSaturation": meta.get("MeanSaturation", 0),
            "MeanValue": meta.get("MeanValue", 0),
            "eccentricity": meta.get("eccentricity", 0),
            "solidity": meta.get("solidity", 0),
        })

    output_file = os.path.join(output_path, "umap_projection.json")
    with open(output_file, "w") as f:
        json.dump(result, f)

    logger.success(f"UMAP projection saved to {output_file}")
    return output_file
