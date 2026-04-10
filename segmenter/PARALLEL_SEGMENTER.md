# Parallel Segmenter — Design & Implementation

## Overview

This document details the parallelization of the PlanktoScope segmenter pipeline, the incremental metadata streaming system, and the removal of the pandas dependency. These changes target the Raspberry Pi 5 (4 cores) and aim for near-linear scaling of image segmentation throughput.

## Problem Statement

The original segmenter processed images sequentially in a single loop within `_pipe()`. On a 4-core RPi 5, three cores sat idle during the CPU-bound image processing (flat correction, thresholding, morphological operations, regionprops extraction, color analysis). Additionally:

- All object metadata accumulated in a Python list in memory until the final EcoTaxa export, increasing peak RAM usage unnecessarily.
- The `pandas` library (60MB on disk) was used solely for a single `DataFrame.to_csv()` call to generate a tab-separated file.

## Architecture

### Before

```
_pipe()
  ├── Calculate flat field (median of first 10 images)
  └── FOR each image (sequential):
        ├── Open image, apply flat correction
        ├── Create binary mask (threshold → erode → dilate → close → erode)
        ├── Slice: label connected components, extract regionprops
        │     ├── For each object: extract morphology, color, blur
        │     ├── Save cropped object JPG
        │     ├── MQTT publish per-object metrics
        │     └── Append object dict to self.__global_metadata["objects"]
        ├── MQTT publish per-image progress
        └── Flat recalculation heuristic (if object count spikes)
  └── ecotaxa_export(): pandas DataFrame → TSV in ZIP archive
```

### After

```
_pipe()
  ├── Calculate flat field (unchanged)
  ├── Create SharedMemory for flat array (zero-copy sharing)
  ├── Create temp .metadata_tmp/ directory
  ├── IF worker_count > 1 AND remove_previous_mask == False:
  │     └── _pipe_parallel() — asyncio + ProcessPoolExecutor
  │           ├── Dispatch process_single_image() per image to worker pool
  │           ├── Each worker: flat correction → mask → slice → write .jsonl
  │           ├── Parent awaits results, publishes MQTT progress
  │           └── On failure: falls back to _pipe_sequential()
  │   ELSE:
  │     └── _pipe_sequential() — original loop with streaming
  │           ├── Preserves flat recalculation heuristic
  │           ├── Preserves remove_previous_mask support
  │           └── Writes .jsonl per image instead of in-memory accumulation
  ├── Assemble all .jsonl files in image order → global_metadata["objects"]
  ├── Cleanup SharedMemory + temp directory
  └── ecotaxa_export(): stdlib csv.writer → TSV in ZIP archive
```

## File Changes

### New Files

#### `segmenter/planktoscope/segmenter/worker.py`

Module-level (picklable) functions for `ProcessPoolExecutor` workers:

- **`worker_init(shm_name, flat_shape, flat_dtype)`** — Called once per worker process at pool startup. Attaches to the parent's `SharedMemory` block and creates a numpy array view of the flat field. This is zero-copy — the ~49MB flat array is not duplicated per worker.

- **`process_single_image(...)`** — The main worker entry point. Receives all parameters as serializable arguments (file paths, scalars, a metadata dict). Performs the complete per-image pipeline:
  1. `cv2.imread()` → divide by shared flat → `rescale_intensity()`
  2. `_create_mask()` — threshold → no_op → erode → dilate → close → erode2
  3. `_slice_image()` — `skimage.measure.label/regionprops`, extract morphology + color + blur per object, save cropped JPGs
  4. Write object metadata to `.jsonl` via `streamer.write_image_objects()`
  5. Return result dict `{image_name, image_index, object_count, duration}`

  Error handling: entire function wrapped in try/except. On failure, logs the error and returns `{image_name, image_index, error: str}` instead of crashing the pool.

- **Pure helper functions** (exact copies from `__init__.py`, made module-level):
  - `_get_color_info(bgr_img, mask)` — HSV mean/std statistics
  - `_extract_metadata_from_regionprop(prop, pixel_size_um=None)` — 24+ morphological features with optional µm calibration via `process_pixel`
  - `_augment_slice(dim_slice, max_dims, size)` — Expand bounding box by padding pixels
  - `_create_mask(img, debug_path, save_debug)` — Mask pipeline with `no_op` hardcoded for the `remove_previous_mask` slot (parallel mode always disables this)
  - `_slice_image(img, name, mask, ...)` — Full object extraction loop. Includes `process_pixel` calibration, threshold value capture, debug image output. No MQTT, no shared state.

#### `segmenter/planktoscope/segmenter/streamer.py`

Incremental metadata I/O using JSON Lines format:

- **`write_image_objects(metadata_dir, image_name, objects)`** — Writes one `.jsonl` file per image. Each line is a JSON object `{"name": "...", "metadata": {...}}` serialized with `NpEncoder` (handles numpy types). File is named `{image_name}.jsonl`, so workers writing different images never conflict.

- **`read_image_objects(filepath)`** — Reads a `.jsonl` file back into a list of dicts.

- **`assemble_all_objects(metadata_dir, images_list)`** — Reads all `.jsonl` files in the order of `images_list` (the sorted image filename list). This guarantees deterministic output order regardless of which worker finished first. Returns the combined object list ready for `ecotaxa_export()`.

### Modified Files

#### `segmenter/planktoscope/segmenter/__init__.py`

**New imports:**
- `planktoscope.segmenter.streamer`
- `planktoscope.segmenter.worker`

**New instance variable:**
- `self.__worker_count = 3` — Default for RPi 5 (4 cores, 1 reserved for Node-RED/system). Configurable via MQTT `settings.worker_count`.

**`_slice_image()` changes:**
- Now returns a 3-tuple: `(object_count, unfiltered_count, objects_list)` instead of `(object_count, unfiltered_count)`.
- Objects are collected in a local `objects_list` and returned, instead of being appended to `self.__global_metadata["objects"]`.
- MQTT per-object publishes remain in place (they execute in the main process during sequential mode).

**`_pipe()` rewrite:**
- Calculates flat field (unchanged).
- Creates `SharedMemory` for the flat array and a temp `.metadata_tmp/` directory.
- Branches to `_pipe_parallel()` or `_pipe_sequential()` based on `worker_count` and `remove_previous_mask`.
- After processing: calls `streamer.assemble_all_objects()` to rebuild the ordered object list.
- Cleanup in `finally` block: `shm.close()`, `shm.unlink()`, `shutil.rmtree(metadata_dir)`.
- Graceful degradation: if parallel dispatch raises an exception, catches it, logs a warning, and falls back to `_pipe_sequential()`.

**`_pipe_parallel()` (new method):**
- Uses `asyncio.run()` scoped to this method only (the rest of the segmenter remains synchronous).
- Creates `ProcessPoolExecutor(max_workers=N, initializer=worker_init)`.
- Dispatches `process_single_image()` per image via `loop.run_in_executor()`.
- Awaits all futures, publishes MQTT progress as each completes.
- Collects errors from failed workers and logs them after the batch.

**`_pipe_sequential()` (new method):**
- Preserves the original sequential loop exactly, including:
  - Flat recalculation heuristic (object count > average + 20)
  - `remove_previous_mask` support
  - Per-image and per-object MQTT publishes
- Only difference: writes objects via `streamer.write_image_objects()` after each image instead of appending to `self.__global_metadata["objects"]`.

**`treat_message()` addition:**
- Parses `settings.worker_count` from MQTT segmentation requests (default: 3).

#### `segmenter/planktoscope/segmenter/ecotaxa.py`

Complete rewrite of the TSV generation, removing the `pandas` and `numpy` dependencies:

- **Removed:** `import pandas`, `import numpy`, `dtype_to_ecotaxa()` function.
- **Added:** `import csv`, `_infer_ecotaxa_type(value)` function — uses `isinstance(value, (int, float))` to determine `[f]` vs `[t]` annotation.
- **`ecotaxa_export()`** now builds rows as a list of dicts, determines column order from the first row, writes using `csv.writer(buf, delimiter="\t")`:
  - Row 1: column names
  - Row 2: EcoTaxa type annotations (`[f]` or `[t]`)
  - Rows 3+: data values
- Output format is identical to the previous pandas-based output.

#### `segmenter/planktoscope/segmenter/operations.py`

Comments added to the module-level globals `__mask_to_remove` and `__last_threshold_value` explaining:
- `__mask_to_remove` is NOT safe for parallel use (requires sequential processing).
- `__last_threshold_value` is safe in parallel mode because each worker process gets its own copy via fork/spawn.

#### `segmenter/pyproject.toml`

- Removed `pandas>=2.3.3,<3` from `dependencies`. No new dependencies added — `asyncio`, `concurrent.futures`, `csv`, `json`, `multiprocessing.shared_memory` are all Python stdlib.

## Key Design Decisions

### Why ProcessPoolExecutor (not threading)?

The segmentation workload is CPU-bound (numpy, opencv, scikit-image). Python's GIL prevents threads from achieving true parallelism for CPU work. `ProcessPoolExecutor` spawns real OS processes that run on separate cores.

### Why SharedMemory for the flat field?

The flat field is a ~49MB float64 array (4056×3040×3). Without shared memory, pickling it into each worker would cost 49MB × N workers in additional memory. `multiprocessing.shared_memory.SharedMemory` provides zero-copy access — all workers read the same physical memory.

### Why JSON Lines (not CSV or SQLite)?

- Each worker writes to a uniquely-named file (`{image_name}.jsonl`), so there's no locking or contention.
- Crash-resilient: if a worker fails, completed images' results survive.
- Assembly in deterministic order is trivial: read files in the sorted `images_list` order.
- JSON naturally handles the nested metadata structure and numpy type conversion (via `NpEncoder`).

### Why disable flat recalculation in parallel mode?

The flat recalculation heuristic checks if the current image's object count exceeds the running average by >20. This creates a sequential feedback loop — you can't know whether to recalculate until the previous image is done. The heuristic was already flagged with `TODO: this heuristic should be improved or removed if deemed unnecessary`. In parallel mode, the flat is computed once from the first 10 images and used for all.

### Why force sequential when remove_previous_mask is enabled?

`remove_previous_mask` subtracts the previous image's mask from the current image's mask. This is a strict image-to-image dependency that cannot be parallelized. When enabled (`remove_previous_mask=True` in MQTT settings), the segmenter automatically falls back to sequential processing.

### Why asyncio.run() scoped to _pipe_parallel() only?

The segmenter runs as a `multiprocessing.Process` with a synchronous main loop polling MQTT every 0.5s. Converting the entire process to async would require replacing `paho-mqtt` with an async MQTT library and restructuring the process lifecycle — a large refactor with marginal benefit since the bottleneck is CPU-bound image processing, not I/O. Scoping `asyncio.run()` to just the parallel dispatch method is the minimal, low-risk approach.

### Why default to 3 workers?

The RPi 5 has 4 cores. Leaving 1 core for Node-RED, MQTT, and system processes prevents the segmenter from starving the dashboard UI. Each worker uses ~150MB for image processing buffers. With the shared flat (~49MB) + parent overhead (~100MB) + 3 workers (~450MB) = ~600MB total, well within the Pi 5's available RAM.

## Memory Profile

| Component | Memory | Notes |
|-----------|--------|-------|
| Flat field (shared) | ~49MB | Single copy via SharedMemory, read by all workers |
| Per-worker image buffers | ~150MB | BGR image + mask + working arrays |
| Parent process overhead | ~100MB | MQTT client, metadata, orchestration |
| **Total (3 workers)** | **~650MB** | Fits comfortably in RPi 5 RAM |
| **Total (1 worker, sequential)** | **~300MB** | Same as original behavior |

## Configuration

### MQTT Settings

The `worker_count` parameter can be sent in the segmentation MQTT message:

```json
{
  "action": "segment",
  "path": "/path/to/images",
  "settings": {
    "worker_count": 3,
    "force": false,
    "recursive": true,
    "ecotaxa": true,
    "keep": true,
    "process_min_ESD": 20,
    "remove_previous_mask": false
  }
}
```

- `worker_count`: Number of parallel workers (default: 3). Set to 1 to force sequential processing.
- `remove_previous_mask`: When `true`, forces sequential processing regardless of `worker_count`.

## Testing Checklist

- [ ] Sequential mode (`worker_count=1`): output identical to pre-refactor
- [ ] Sequential mode with `remove_previous_mask=true`: behavior preserved
- [ ] Parallel mode (`worker_count=3`): same objects detected, same EcoTaxa TSV content (order is deterministic because assembly reads in image-list order)
- [ ] Parallel mode with image processing failure: error logged, remaining images processed, pipeline completes
- [ ] EcoTaxa ZIP archive: TSV format matches expectations (2-row header with `[f]`/`[t]` annotations)
- [ ] MQTT dashboard: progress updates still appear during segmentation
- [ ] Memory: RSS stays within expected bounds during parallel run
- [ ] `process_pixel` calibration: µm/µm² measurements correct in both modes
- [ ] Threshold value captured in object metadata in both modes
