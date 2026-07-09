"""Generate self-contained design sandboxes for BOTH report surfaces.

Renders the live templates (template.html + template_onepage.html) with REAL
Chase_1_4 data via ``report_generator.build_context``, but swaps every heavy
base64 image (flat field, charts, ROI thumbnails) for small labelled gray SVG
placeholders so the files stay tiny and artifact-friendly. The brand logo stays
real (it's tiny).

Charts are restyled in Python (the ``chart_*`` functions in report_generator),
NOT in the HTML — so using placeholders here loses none of the HTML-editable
design. Open the two .html files in a browser / Claude artifact, iterate the
markup + CSS, then send them back to re-bind (see HANDOFF.md).

Outputs (cwd): sandbox_full.html, sandbox_onepage.html, sample_context.json
Usage: python make_sandbox.py [acquisition_img_path]
"""
import sys
import json
import base64
from pathlib import Path

sys.path.insert(0, "/opt/PlanktoScope/reporter")
import report_generator as R
from jinja2 import Environment, FileSystemLoader, select_autoescape

ACQ = sys.argv[1] if len(sys.argv) > 1 else "/home/pi/data/img/2026-05-20/Chase_1/Chase_1_4"


def ph(w, h, label):
    """A labelled gray placeholder as an SVG data-URI (keeps the real aspect)."""
    svg = (f"<svg xmlns='http://www.w3.org/2000/svg' width='{w}' height='{h}'>"
           f"<rect width='100%' height='100%' fill='#eef1f5' stroke='#cdd5df'/>"
           f"<text x='50%' y='50%' font-family='Helvetica' font-size='{max(10, h // 8)}' "
           f"fill='#9aa4b2' text-anchor='middle' dominant-baseline='middle'>{label}</text></svg>")
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()


full_ctx, panel_ctx, name = R.build_context(ACQ)

# --- swap heavy images for placeholders (brand_logo stays real) -------------
# gallery is the same list object in both contexts, so this covers both.
for t in full_ctx["gallery"]:
    t["img"] = ph(120, 90, "ROI")

full_ctx["flat_field"] = ph(800, 600, "FLAT FIELD")
full_ctx["chart_esd"] = ph(760, 280, "chart_esd")
full_ctx["chart_sharpness"] = ph(760, 280, "chart_sharpness")
full_ctx["chart_heatmap"] = ph(640, 470, "chart_heatmap")

panel_ctx["chart_esd"] = ph(380, 265, "chart_esd")
panel_ctx["chart_sharpness"] = ph(380, 265, "chart_sharpness")
panel_ctx["chart_heatmap"] = ph(380, 265, "chart_heatmap")
panel_ctx["chart_concentration"] = ph(380, 265, "chart_concentration")

env = Environment(loader=FileSystemLoader(str(R.HERE)),
                  autoescape=select_autoescape(["html"]))
out_full = env.get_template("template.html").render(**full_ctx)
out_one = env.get_template("template_onepage.html").render(**panel_ctx)
Path("sandbox_full.html").write_text(out_full)
Path("sandbox_onepage.html").write_text(out_one)


# --- data-contract dump: real values, image blobs abbreviated ---------------
def describe(v):
    if isinstance(v, str) and v.startswith("data:"):
        return f"<{v[5:v.find(';')]} base64, {len(v)} chars>"
    if isinstance(v, list):
        head = [describe(x) for x in v[:2]]
        return head + ([f"...(+{len(v) - 2} more, {len(v)} total)"] if len(v) > 2 else [])
    if isinstance(v, dict):
        return {k: describe(x) for k, x in v.items()}
    return v


dump = {k: describe(v) for k, v in full_ctx.items()}
dump["chart_concentration"] = describe(panel_ctx["chart_concentration"])
dump["_one_pager_only"] = ["chart_concentration"]
Path("sample_context.json").write_text(json.dumps(dump, indent=2, default=str))

print("sandbox_full.html bytes:", len(out_full))
print("sandbox_onepage.html bytes:", len(out_one))
print("gallery tiles:", len(full_ctx["gallery"]))
