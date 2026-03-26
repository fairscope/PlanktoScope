"""Incremental metadata streaming to disk and assembly for EcoTaxa export.

Each image's segmented objects are written to a separate .jsonl file during processing.
After all images are done, the files are assembled in image order for deterministic output.
"""

import json
import os

from loguru import logger

from planktoscope.segmenter.encoder import NpEncoder


def write_image_objects(metadata_dir: str, image_name: str, objects: list[dict]) -> str:
    """Write per-image object metadata to a .jsonl file.

    Args:
        metadata_dir: Directory for intermediate metadata files
        image_name: Base name of the source image (no extension)
        objects: List of object dicts, each with "name" and "metadata" keys

    Returns:
        Path to the written .jsonl file
    """
    os.makedirs(metadata_dir, exist_ok=True)
    filepath = os.path.join(metadata_dir, f"{image_name}.jsonl")
    with open(filepath, "w") as f:
        for obj in objects:
            f.write(json.dumps(obj, cls=NpEncoder) + "\n")
    logger.debug(f"Wrote {len(objects)} objects to {filepath}")
    return filepath


def read_image_objects(filepath: str) -> list[dict]:
    """Read object metadata from a .jsonl file.

    Args:
        filepath: Path to a .jsonl file written by write_image_objects

    Returns:
        List of object dicts
    """
    objects = []
    with open(filepath, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                objects.append(json.loads(line))
    return objects


def assemble_all_objects(metadata_dir: str, images_list: list[str]) -> list[dict]:
    """Read all per-image .jsonl files in image order and return combined object list.

    Args:
        metadata_dir: Directory containing .jsonl files
        images_list: Ordered list of image filenames (with extension)

    Returns:
        Combined list of all object dicts, in image order
    """
    all_objects = []
    for filename in images_list:
        image_name = os.path.splitext(filename)[0]
        filepath = os.path.join(metadata_dir, f"{image_name}.jsonl")
        if os.path.exists(filepath):
            image_objects = read_image_objects(filepath)
            all_objects.extend(image_objects)
            logger.debug(f"Assembled {len(image_objects)} objects from {image_name}")
        else:
            logger.warning(f"No metadata file found for {image_name}")
    logger.info(f"Assembled {len(all_objects)} total objects from {len(images_list)} images")
    return all_objects
