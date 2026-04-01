#!/usr/bin/env python3
"""Update Node-RED flows.json to implement per-preset calibration matrix.

Run on the Pi:  python3 update_flows_calibration_matrix.py

Changes:
  1. "set calibration_pixel_size" node — stores user calibration per-preset in
     global context calibration_matrix, not just bare globals.
  2. "set acq_params" node — removes process_pixel_size→process_pixel sync hack;
     handles process_pixel directly.
  3. "body" ui-template — applyMagChange() resolves pixel size from calibration
     matrix; sendSettings() sends process_pixel instead of process_pixel_size.
  4. "Get Global Variables" function node — initializes calibration_matrix in
     global context if missing (first boot / migration).
"""

import json
import shutil
import sys
from pathlib import Path

FLOWS_PATH = Path("/home/pi/PlanktoScope/node-red/projects/dashboard/flows.json")

# ── Node IDs ──────────────────────────────────────────────────────────────────
BODY_TEMPLATE_ID = "79bccc0355eb5d87"
SET_CALIBRATION_ID = "133c27ef75317205"
SET_ACQ_PARAMS_ID = "74aa092817adc6f0"
GET_GLOBALS_ID = "31fab063b7078fe6"


def patch_set_calibration(node):
    """Rewrite 'set calibration_pixel_size' to store per-preset calibration."""
    node["func"] = """\
if (msg.topic) {
    const pixelSize = msg.payload.calibration_pixel_size;
    const currentMag = global.get("acq_magnification") || "medium";

    // Update per-preset calibration matrix (persistent global context)
    let matrix = global.get("calibration_matrix") || {
        "high":   { "factory": 0.53, "user_calibrated": null },
        "medium": { "factory": 0.75, "user_calibrated": null },
        "low":    { "factory": 1.34, "user_calibrated": null }
    };
    matrix[currentMag].user_calibrated = pixelSize;
    global.set("calibration_matrix", matrix);

    // Keep legacy globals for backward compatibility
    global.set("process_pixel", pixelSize);
    global.set("process_pixel_size", pixelSize);
    global.set("calibration_pixel_size", pixelSize);

    // Store other calibration parameters
    global.set("calibration_scale_factor", msg.payload.calibration_scale_factor);
    global.set("calibration_sensor_width", msg.payload.calibration_sensor_width);
    global.set("calibration_stream_width", msg.payload.calibration_stream_width);
    global.set("calibration_known_distance", msg.payload.calibration_known_distance);
    global.set("calibration_measured_distance", msg.payload.calibration_measured_distance);
    global.set("calibration_markerA_x", msg.payload.calibration_markerA_x);
    global.set("calibration_markerA_y", msg.payload.calibration_markerA_y);
    global.set("calibration_markerB_x", msg.payload.calibration_markerB_x);
    global.set("calibration_markerB_y", msg.payload.calibration_markerB_y);

    node.warn("Calibration saved for preset '" + currentMag + "': " + pixelSize + " µm/px");
}
return msg;"""


def patch_set_acq_params(node):
    """Simplify 'set acq_params' — handle process_pixel directly, drop sync hack."""
    node["func"] = """\
// On récupère le payload
const p = msg.payload;

// On ne procède que si le payload est un objet
if (p && typeof p === 'object') {

    // Liste des paramètres à surveiller et à stocker
    const keys = [
        "acq_id", "acq_nb_frame", "acq_interframe_volume",
        "acq_imaged_volume", "acq_pumped_volume", "acq_comment",
        "acq_status", "acq_magnification", "acq_tube_lens_reference",
        "acq_objective_lens_reference", "process_pixel",
        "calibration_pixel_size", "calibration_led_intensity",
        "sensor_width_um", "sensor_height_um", "acq_flowcell_thickness",
        "acq_interframe_flowrate", "acq_stabilization_delay",
        "acq_start_timestamp"
    ];

    keys.forEach(key => {
        if (p[key] !== undefined) {
            global.set(key, p[key]);
        }
    });

    // Cas particuliers (noms de propriétés différents entre msg et global)
    if (p.progression !== undefined) global.set("acq_progression", p.progression);
    if (p.duration_left !== undefined) global.set("acq_duration_left", p.duration_left);
}

return msg;"""


def patch_get_globals(node):
    """Add calibration matrix initialization to Get Global Variables."""
    node["func"] = """\
// Initialize calibration matrix on first boot / migration
let matrix = global.get("calibration_matrix");
if (!matrix) {
    matrix = {
        "high":   { "factory": 0.53, "user_calibrated": null },
        "medium": { "factory": 0.75, "user_calibrated": null },
        "low":    { "factory": 1.34, "user_calibrated": null }
    };
    global.set("calibration_matrix", matrix);
}

const keys = global.keys();
msg.payload = {};

keys.forEach(key => {
    if (!key.startsWith('$')) {
        msg.payload[key] = global.get(key);
    }
});

return msg;"""


def patch_body_template(node):
    """Patch the body ui-template for calibration matrix support."""
    fmt = node["format"]

    # ── 1. Add calibrationMatrix to data() ────────────────────────────────
    fmt = fmt.replace(
        "calibration_pixel_size: 0.75,",
        "calibration_pixel_size: 0.75,\n"
        "      calibrationMatrix: {\n"
        '        high:   { factory: 0.53, user_calibrated: null },\n'
        '        medium: { factory: 0.75, user_calibrated: null },\n'
        '        low:    { factory: 1.34, user_calibrated: null }\n'
        "      },",
        1,  # only first occurrence
    )

    # ── 2. Handle calibration_matrix in msg watcher ───────────────────────
    # After the existing calibration_pixel_size handler, add matrix handler.
    # Find the line that processes incoming calibration_pixel_size
    old_cal_handler = (
        "if (p.calibration_pixel_size !== undefined) "
        "this.calibration_pixel_size = Number(p.calibration_pixel_size);\n"
        "        if (p.process_pixel_size !== undefined) "
        "this.calibration_pixel_size = Number(p.process_pixel_size);"
    )
    new_cal_handler = (
        "if (p.calibration_pixel_size !== undefined) "
        "this.calibration_pixel_size = Number(p.calibration_pixel_size);\n"
        "        if (p.process_pixel !== undefined) "
        "this.calibration_pixel_size = Number(p.process_pixel);\n"
        "\n"
        "        // Load calibration matrix from global context\n"
        "        if (p.calibration_matrix) {\n"
        "          this.calibrationMatrix = p.calibration_matrix;\n"
        "        }"
    )
    if old_cal_handler not in fmt:
        print("WARNING: Could not find calibration handler block to patch.", file=sys.stderr)
        print("  Looking for:", repr(old_cal_handler[:80]), file=sys.stderr)
    else:
        fmt = fmt.replace(old_cal_handler, new_cal_handler, 1)

    # ── 3. Patch applyMagChange() — resolve from calibration matrix ───────
    old_apply_pixel = (
        "this.calibration_pixel_size       = config.pixel_size;"
    )
    new_apply_pixel = (
        "// Resolve pixel size: user calibration wins over factory default\n"
        "        const calEntry = this.calibrationMatrix[this.currentMag];\n"
        "        this.calibration_pixel_size = "
        "(calEntry && calEntry.user_calibrated !== null)\n"
        "          ? calEntry.user_calibrated\n"
        "          : config.pixel_size;"
    )
    if old_apply_pixel not in fmt:
        print("WARNING: Could not find applyMagChange pixel_size assignment.", file=sys.stderr)
    else:
        fmt = fmt.replace(old_apply_pixel, new_apply_pixel, 1)

    # ── 4. sendSettings(): send process_pixel instead of process_pixel_size
    old_send = "process_pixel_size:             this.calibration_pixel_size,"
    new_send = "process_pixel:                  this.calibration_pixel_size,"
    if old_send not in fmt:
        print("WARNING: Could not find process_pixel_size in sendSettings.", file=sys.stderr)
    else:
        fmt = fmt.replace(old_send, new_send, 1)

    # ── 5. Patch preset reverse-lookup to use process_pixel ───────────────
    old_reverse = (
        "} else if (p.process_pixel_size || p.calibration_pixel_size) {\n"
        "          const size = Number(p.process_pixel_size || p.calibration_pixel_size);"
    )
    new_reverse = (
        "} else if (p.process_pixel || p.calibration_pixel_size) {\n"
        "          const size = Number(p.process_pixel || p.calibration_pixel_size);"
    )
    if old_reverse not in fmt:
        print("WARNING: Could not find preset reverse-lookup to patch.", file=sys.stderr)
    else:
        fmt = fmt.replace(old_reverse, new_reverse, 1)

    node["format"] = fmt


def main():
    if not FLOWS_PATH.exists():
        print(f"ERROR: {FLOWS_PATH} not found", file=sys.stderr)
        sys.exit(1)

    # Backup
    backup = FLOWS_PATH.with_suffix(".json.bak")
    shutil.copy2(FLOWS_PATH, backup)
    print(f"Backup saved to {backup}")

    with open(FLOWS_PATH) as f:
        flows = json.load(f)

    nodes = {n.get("id"): n for n in flows}

    # Patch each node
    patchers = {
        SET_CALIBRATION_ID: ("set calibration_pixel_size", patch_set_calibration),
        SET_ACQ_PARAMS_ID: ("set acq_params", patch_set_acq_params),
        GET_GLOBALS_ID: ("Get Global Variables", patch_get_globals),
        BODY_TEMPLATE_ID: ("body template", patch_body_template),
    }

    for node_id, (label, patcher) in patchers.items():
        node = nodes.get(node_id)
        if node is None:
            print(f"WARNING: Node '{label}' ({node_id}) not found!", file=sys.stderr)
            continue
        patcher(node)
        print(f"Patched: {label} ({node_id})")

    with open(FLOWS_PATH, "w") as f:
        json.dump(flows, f, indent=4)

    print(f"\nDone. Restart Node-RED to apply: sudo systemctl restart nodered")


if __name__ == "__main__":
    main()
