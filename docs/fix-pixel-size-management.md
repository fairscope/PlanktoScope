# Fix: Pixel Size Management System

## Problem Statement

Users reported three related issues when using different flowcell sizes (100µm, 300µm, 500µm):

1. **Wrong ESD filtering thresholds** — The segmenter was not respecting the 20µm minimum ESD target. The 300µm flowcell filtered at ~15µm instead of 20µm; the 100µm and 500µm flowcells had similarly incorrect cutoffs.
2. **Pixel size missing from TSV output** — All exported EcoTaxa TSV files had the same (absent) pixel size, regardless of configuration. Downstream biovolume and size calculations were therefore incorrect.
3. **Measurements in pixels instead of µm** — All morphological measurements (area, major/minor axis, equivalent diameter, etc.) were exported in raw pixel units, not physical units.

## Optical Configurations

The PlanktoScope supports three magnification presets, each with a different lens configuration and pixel-to-µm ratio:

| Magnification | Tube Lens | Objective | Pixel Size | Flowcell | Min ESD (20µm) |
|---|---|---|---|---|---|
| **high** | 35mm F2.4 | 12mm F2 | **0.53 µm/px** | 100µm | 37.7 px |
| **medium** | 25mm F1.8 | 12mm F1.8 | **0.75 µm/px** | 300µm | 26.7 px |
| **low** | 25mm F2.0 | 21.8mm F2.8 | **1.34 µm/px** | 500µm | 14.9 px |

Users can also run interactive pixel calibration to measure the exact µm/px ratio for their specific hardware.

## Root Cause

Two distinct issues prevented `process_pixel` from reaching the segmenter:

### Issue 1: Naming mismatch between Node-RED and Python

The Node-RED acquisition page sends the pixel size as **`process_pixel_size`** in the MQTT config. The Python segmenter expects **`process_pixel`**. These are different field names:

- The calibration page sets `global("process_pixel")` — correct name, but only when user runs calibration
- The acquisition page magnification presets set `this.calibration_pixel_size` and send it as `process_pixel_size` — wrong name for the segmenter
- The `set acq_params` Node-RED function stored `process_pixel_size` in globals but never synced it to `process_pixel`
- When the user changed magnification on the acquisition page, the `process_pixel` global remained stale at whatever value was last set by calibration (or never set at all)

### Issue 2: No fallback when both fields were missing

If the user never ran calibration and the Node-RED globals contained neither field with the right name, `process_pixel` never reached `metadata.json` at all. The segmenter fell back to treating all measurements as raw pixels.

### Data flow before the fix

```
Node-RED Acquisition Page                    Calibration Page
  sends: process_pixel_size: 0.53             sets global("process_pixel") = 0.82
           |                                            |
           ▼                                            ▼
  set acq_params:                             set calibration_pixel_size:
    global("process_pixel_size") = 0.53         global("process_pixel") = 0.82
    ✗ process_pixel NOT updated                 ✗ dead end (no wires out)
           |                                            |
           ▼                                            ▼
  update_config gathers all process_* globals:
    → process_pixel_size = 0.53 (current)
    → process_pixel = 0.82 (stale from calibration, or absent)
           |
           ▼
  MQTT: imager/image/update_config
    → config includes BOTH fields (or only process_pixel_size)
           |
           ▼
  Imager: self._metadata → metadata.json
    → process_pixel = 0.82 (stale!) or absent
    → segmenter uses wrong value or no value
```

### Cascade of failures per magnification

| Flowcell | Pixel Size | Bug: ESD threshold | Effective ESD | Expected |
|---|---|---|---|---|
| 100µm (high) | 0.53 µm/px | 20 px (treated as pixels) | **10.6 µm** | 20 µm |
| 300µm (medium) | 0.75 µm/px | 20 px | **15.0 µm** | 20 µm |
| 500µm (low) | 1.34 µm/px | 20 px | **26.8 µm** (loses 20-27µm objects) | 20 µm |

### Why 15µm instead of 20µm (the math)

The segmenter's min ESD filter works like this:

```python
# With process_pixel = 0.75:
min_esd_pixels = 20 / 0.75 = 26.67 pixels  ← CORRECT (matches 20µm)

# Without process_pixel (fallback):
min_esd_pixels = 20  ← treats µm value as pixels
# 20 pixels × 0.75 µm/px = 15µm effective threshold ← BUG
```

## Fix

### Change 1: Use `process_pixel` from Node-RED calibration matrix

**File:** `controller/imager/main.py`

Node-RED resolves the correct pixel size from a per-preset calibration matrix (user calibration wins over factory default) and sends it as `process_pixel`. The imager simply uses it:

```python
pixel_size = metadata.get("process_pixel")
if pixel_size is not None:
    metadata["process_pixel"] = float(pixel_size)
else:
    loguru.logger.warning("process_pixel missing from config — measurements will be in pixels")
```

**Key design decisions:**

- **Node-RED is the resolver** — The calibration matrix (factory defaults + per-preset user calibrations) lives in Node-RED. Python is a consumer, not a resolver.
- **No fallback** — Backend and frontend are shipped together, so Node-RED always sends `process_pixel`. No need for `process_pixel_fixed` from `hardware.json`.
- **Stateless** — The resolution happens at metadata-creation time for each acquisition. No state accumulates across `update_config` calls.

### Change 1b: Node-RED calibration matrix

**File:** `node-red/projects/dashboard/flows.json` (changes made in flow editor)

- **`set acq_params`** — stores `process_pixel` (resolved value) directly
- **`set calibration_pixel_size`** — writes user calibration to `calibration_matrix[preset].user_calibrated` in global context
- **Body template `applyMagChange()`** — resolves from calibration matrix: `user_calibrated ?? factory`
- **Body template `sendUpdate()`** — sends `process_pixel` (resolved) instead of `process_pixel_size`
- **`Get Global Variables`** — initializes `calibration_matrix` on first boot

### Change 2: Update EcoTaxa archive naming convention

**Files:** `segmenter/planktoscope/segmenter/__init__.py`, `segmenter/planktoscope/segmenter/ecotaxa.py`

Archive and internal TSV filenames now follow the format:

| Component | Old Format | New Format |
|---|---|---|
| ZIP archive | `ecotaxa_{acquisition}.zip` | `Ecotaxa_{project}_{acquisition}.zip` |
| TSV inside archive | `ecotaxa_{acquisition_id}.tsv` | `Ecotaxa_{project}_{acquisition_id}.tsv` |

Both `project` (from `sample_project`) and `acquisition` (from `acq_id`) are sanitized by replacing spaces with underscores, consistent with existing behavior.

## What did NOT need changing

The segmenter's core logic was already correct — it just wasn't receiving the data it needed:

- **ESD filtering** (`__init__.py:460-462`) — Correctly uses `region.equivalent_diameter_area` (derived from object area, NOT vignette/bounding box area)
- **Measurement scaling** (`__init__.py:334-399`) — Correctly multiplies linear measurements by `px` and area measurements by `px²`
- **Metadata filter** (`__init__.py:806-812`) — `process_pixel` starts with "process" and correctly passes the prefix filter
- **TSV export** (`ecotaxa.py:247-256`) — Correctly includes all global metadata fields in the output

## Verification

With `process_pixel` now correctly resolved for all magnifications:

| Magnification | Pixel Size | Min ESD Threshold | Effective ESD | Correct? |
|---|---|---|---|---|
| high (100µm) | 0.53 µm/px | `20 / 0.53 = 37.7 px` | 20.0 µm | ✓ |
| medium (300µm) | 0.75 µm/px | `20 / 0.75 = 26.7 px` | 20.0 µm | ✓ |
| low (500µm) | 1.34 µm/px | `20 / 1.34 = 14.9 px` | 20.0 µm | ✓ |

Additional verifications:

| Step | Value | Correct? |
|---|---|---|
| Area measurement | `prop.area × pixel_size²` µm² | ✓ |
| Equivalent diameter | `prop.equivalent_diameter × pixel_size` µm | ✓ |
| `process_pixel` in TSV | Matches selected magnification | ✓ |
| ESD uses object area | `equivalent_diameter_area` (not bbox) | ✓ |
| Calibration page value | Flows through and overrides presets | ✓ |
| Magnification change | `process_pixel_size` overrides stale `process_pixel` | ✓ |

### Change 3: Visualizer TSV file discovery

**File:** `lib/db.js`

The `getSegmentationFromPath()` function scans directories for EcoTaxa TSV files to populate the visualizer. It previously only matched the lowercase `ecotaxa_` prefix, so segmentations created with the new `Ecotaxa_` naming were invisible.

```javascript
// Before
if (extension === ".tsv" && file.startsWith("ecotaxa_")) {

// After — accepts both naming conventions
if (extension === ".tsv" && (file.startsWith("Ecotaxa_") || file.startsWith("ecotaxa_"))) {
```

This ensures backward compatibility with existing datasets while supporting the new naming format.

### Change 4: Node-RED flow function patches

**File:** `node-red/projects/dashboard/flows.json` (tracked in dashboard subrepo)

Four function nodes in the Visualizer tab referenced hardcoded lowercase `ecotaxa_` patterns:

#### "Get tsv path" (×2 nodes)

The `expectedTsv` lookup now tries the new naming format first, falling back to legacy:

```javascript
// Before
const expectedTsv = `${cleanPath}/ecotaxa_${acqId}.tsv`;

// After — try new format first, then legacy
const newTsv = `${cleanPath}/Ecotaxa_${acqId}.tsv`;
const legacyTsv = `${cleanPath}/ecotaxa_${acqId}.tsv`;
const expectedTsv = fs.existsSync(newTsv) ? newTsv : legacyTsv;
```

The fallback `files.find()` also accepts both prefixes:

```javascript
// Before
const tsvFile = files.find(f => f.startsWith('ecotaxa_') && f.endsWith('.tsv'));

// After
const tsvFile = files.find(f => (f.startsWith('Ecotaxa_') || f.startsWith('ecotaxa_')) && f.endsWith('.tsv'));
```

#### "Insert export column" (×2 nodes)

The export ZIP URL now includes the project name and uses the new prefix:

```javascript
// Before
item.export = `/ps/data/browse/api/raw/export/ecotaxa/ecotaxa_${acq}.zip`;

// After
const project = (item.project_name || '').replace(/ /g, '_');
item.export = `/ps/data/browse/api/raw/export/ecotaxa/Ecotaxa_${project}_${acq}.zip`;
```

## Files Changed

| File | Lines | Description |
|---|---|---|
| `controller/imager/main.py` | 179-187 | Use `process_pixel` from Node-RED; warn if missing |
| `segmenter/planktoscope/segmenter/__init__.py` | 855-858 | Update archive filename to `Ecotaxa_{project}_{acquisition}.zip` |
| `segmenter/planktoscope/segmenter/ecotaxa.py` | 272-275 | Update TSV filename to `Ecotaxa_{project}_{acquisition_id}.tsv` |
| `lib/db.js` | 192 | Accept both `Ecotaxa_` and `ecotaxa_` prefixes in visualizer TSV discovery |
| `lib/file-config.js` | 18-35 | Calibration file init consolidated into `initConfigFiles()` |
| `default-configs/calibration.json` | — | Per-preset factory defaults for the calibration matrix |
| `segmenter/tests/test_pixel_size.py` | — | Pytest tests for pixel size pipeline |
| `node-red/.../flows.json` | — | Calibration matrix + Ecotaxa_ naming (via flow editor) |

## Backward Compatibility

All file-discovery code (db.js, Node-RED flow functions) accepts **both** the new `Ecotaxa_` and legacy `ecotaxa_` prefixes. Existing datasets produced before this fix remain fully visible and functional. Only newly created archives and TSV files use the new naming convention.

## Related Context

- Three magnification presets exist: high (0.53), medium (0.75), low (1.34) — each corresponds to a different lens pair and flowcell thickness
- Per-preset calibration matrix in `calibration.json` stores factory defaults and optional user calibrations; see `docs/calibration-matrix.md`
- Users can override factory presets via the interactive pixel calibration page (per-preset, preserved across magnification switches)
- The segmenter's `process_min_ESD` defaults to 20µm (configurable via MQTT segment command's `settings.process_min_ESD`)
- The old filtering approach (comparing `acq_minimum_mesh` against `filled_area`) was previously replaced with the current ESD-based approach per the CHANGELOG
