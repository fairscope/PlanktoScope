# Per-Preset Calibration Matrix

## Problem

The original pixel size management used a single global `process_pixel` value. When a user switched magnification presets, the factory default for the new preset overwrote any user calibration. A stage-micrometer calibration (the gold standard in microscopy) could be silently discarded.

| Scenario | Expected | Old behavior |
|---|---|---|
| User calibrates medium optics to 0.762 µm/px, starts acquisition on "medium" | Uses 0.762 | Uses 0.75 (factory overwrites calibration) |
| User calibrates high, switches to medium, switches back to high | Restores high calibration | Uses 0.53 (factory value, calibration lost) |

## Solution

Each magnification preset (high/medium/low) stores both its factory default and an optional user-calibrated override. The active pixel size is always: **user calibration if it exists for that preset, otherwise factory default**.

```
calibration_matrix = {
    "high":   { "factory": 0.53, "user_calibrated": null },
    "medium": { "factory": 0.75, "user_calibrated": null },
    "low":    { "factory": 1.34, "user_calibrated": null }
}
```

Resolution happens in Node-RED before sending to Python. Python is a consumer, not a resolver.

## Data Flow

```
User selects preset or completes calibration
        │
        ▼
┌──────────────────────────┐
│  Node-RED (body template)│
│                          │
│  calibrationMatrix       │
│  resolves: user_cal ??   │
│  factory default         │
│                          │
│  sends process_pixel     │
│  via MQTT                │
└──────────┬───────────────┘
           │  MQTT: imager/image/update_config
           ▼
┌──────────────────────────┐
│  Python Imager           │
│  (controller/imager/     │
│   main.py)               │
│                          │
│  Uses process_pixel      │
│  directly. Fallback:     │
│  process_pixel_fixed     │
│  from hardware.json      │
│                          │
│  Writes → metadata.json  │
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│  Segmenter               │
│  (__init__.py)            │
│                          │
│  Reads process_pixel     │
│  from metadata.json      │
│                          │
│  • ESD threshold (µm→px) │
│  • Measurement scaling   │
│  • Writes to TSV         │
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│  Gallery / Explorer      │
│  (Node-RED templates)    │
│                          │
│  Reads process_pixel     │
│  from TSV column         │
│  → meta.resolution       │
│                          │
│  • Scale bar rendering   │
│  • Thumbnail sizing      │
│  • Measurement display   │
└──────────────────────────┘
```

## Files Changed

### Python

#### `controller/imager/main.py` (lines 179–193)

**Before:** 3-tier resolution cascade:
1. `process_pixel_size` (preset from acquisition page) — wins
2. `process_pixel` (from calibration page) — loses if preset set
3. `process_pixel_fixed` (hardware.json fallback)

**After:** Node-RED always sends the resolved value. Python just uses it:

```python
pixel_size = metadata.get("process_pixel")
if pixel_size is not None:
    metadata["process_pixel"] = float(pixel_size)
else:
    loguru.logger.warning("process_pixel missing from config — measurements will be in pixels")
```

### JavaScript

#### `lib/file-config.js`

Added:
- `CALIBRATION_PATH` — `/opt/PlanktoScope/calibration.json`
- `readCalibrationConfig()` — read the calibration matrix
- `updateCalibrationConfig()` — update it
- `hasCalibrationConfig()` — check existence
- Calibration file init moved into `initConfigFiles()` with copy-if-missing semantics (never overwrites user calibrations)

#### `default-configs/calibration.json`

Factory defaults for the calibration matrix. Created during hardware setup if it doesn't already exist.

### Node-RED Flow Changes

Changes made directly in the Node-RED flow editor.

#### `Get Global Variables` (id: `31fab063b7078fe6`)

Added initialization of `calibration_matrix` in persistent global context on first boot. If the global doesn't exist, creates it with factory defaults. This matrix is then sent to the body template along with all other globals when the acquisition page loads.

#### `set calibration_pixel_size` (id: `133c27ef75317205`)

**Before:** Wrote calibration result to three bare globals (`process_pixel`, `process_pixel_size`, `calibration_pixel_size`).

**After:** Reads `acq_magnification` from global context to determine current preset, then writes the calibrated value to `calibration_matrix[preset].user_calibrated` in persistent global context. Still writes legacy globals for backward compatibility. Logs which preset was calibrated.

#### `set acq_params` (id: `74aa092817adc6f0`)

**Before:** Stored `process_pixel_size` in global context and synced it to `process_pixel` via a manual hack.

**After:** Stores `process_pixel` directly (the resolved value from the calibration matrix). Removed `process_pixel_size` from the key list. Removed the sync hack.

#### Body template (id: `79bccc0355eb5d87`)

**`data()` section:**
Added `calibrationMatrix` property initialized with factory defaults.

**Message watcher:**
- Loads `calibration_matrix` from incoming globals into `this.calibrationMatrix`
- Changed `process_pixel_size` handler to `process_pixel`

**`applyMagChange()` method:**
Instead of always setting `this.calibration_pixel_size = config.pixel_size` (factory), now resolves from the calibration matrix:
```javascript
const calEntry = this.calibrationMatrix[this.currentMag];
this.calibration_pixel_size = (calEntry && calEntry.user_calibrated !== null)
  ? calEntry.user_calibrated
  : config.pixel_size;
```

**`sendSettings()` method:**
Sends `process_pixel` (resolved value) instead of `process_pixel_size` (factory value).

### Unchanged

- **Segmenter** (`segmenter/planktoscope/segmenter/__init__.py`) — reads `process_pixel` from metadata.json as before. ESD filtering, measurement scaling, and metadata prefix filtering are unchanged.
- **EcoTaxa export** (`ecotaxa.py`) — unchanged, uses scaled values from segmenter.
- **Gallery/Explorer function nodes** — unchanged. They parse `process_pixel` from TSV columns, not from live MQTT globals.
- **Gallery/Explorer UI templates** — unchanged. Scale bar rendering (`getScaleBar`, `adaptiveScaleMicrons`, `scaleBarPercent`, `displayPx`) reads `meta.resolution` which comes from TSV parsing.

## MQTT Contract

| Field | Before | After |
|---|---|---|
| `process_pixel_size` | Sent by acquisition page (factory preset value) | No longer sent |
| `process_pixel` | Set by calibration page via global context | Resolved value from calibration matrix |

## Backward Compatibility

**Existing installations without `calibration.json`:** `Get Global Variables` initializes `calibration_matrix` in global context with factory defaults on first boot. `initConfigFiles()` creates the JSON file from defaults during hardware setup without overwriting existing calibrations.

## Scale Bar Impact

The Gallery and Explorer scale bars read `process_pixel` from the EcoTaxa TSV file at display time — not from live MQTT globals. The data path is:

1. `process_pixel` written to `metadata.json` during acquisition
2. Segmenter reads it, writes it to TSV as a column
3. Gallery/Explorer function nodes parse TSV → `meta.resolution`
4. UI templates use `meta.resolution` for `getScaleBar()`, `displayPx()`, `scaleBarPercent()`

Since `process_pixel` still reaches metadata.json with the correct value, scale bars are unaffected.
