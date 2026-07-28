#!/usr/bin/env python3
"""PlanktoScope PDF report generator.

Subscribes to ``actuator/reporter/generate``. On each message it reads an
acquisition's metadata.json + EcoTaxa TSV + flat field + ROI thumbnails,
computes the same QC statistics the Validation dashboard shows (the JS logic
is ported verbatim so the PDF matches the screen), renders an HTML template,
and converts it to a self-contained PDF with WeasyPrint. Completion (or
failure) is published to ``status/reporter``.

Trigger payload:  {"action": "generate",
                   "acquisition_path": "/home/pi/data/img/<date>/<sample>/<acq>"}
"""

import asyncio
import base64
import csv
import io
import json
import math
import os
import re
import statistics
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

import aiomqtt
import numpy as np
from PIL import Image, ImageFilter

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.ticker import FixedLocator, FuncFormatter
from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
MQTT_HOST = os.environ.get("REPORTER_MQTT_HOST", "localhost")
MQTT_PORT = int(os.environ.get("REPORTER_MQTT_PORT", "1883"))
TOPIC_IN = "actuator/reporter/generate"
TOPIC_OUT = "status/reporter"

REPORTS_DIR = Path(os.environ.get("REPORTER_OUTPUT", "/home/pi/data/reports"))
HARDWARE_JSON = Path("/home/pi/PlanktoScope/hardware.json")
HERE = Path(__file__).resolve().parent
FONTS_DIR = HERE / "fonts"

# Dashboard colors (match the Validation page)
BLUE = "#1565C0"    # flowing
AMBER = "#F59E0B"   # stuck
GREY = "#9CA3AF"

# Thresholds — kept identical to the dashboard QC function nodes.
SHARP_LAPLACIAN_MIN = 0.176   # >= this == in focus  (~P40 of new ratio metric)
BLURRY_LAPLACIAN_MAX = 0.086  # <  this == blurry    (~P10 of new ratio metric)
STUCK_BIN_PX = 60
STUCK_MIN_FRAMES = 8
SENSOR_ACROSS = 3040        # object_x range
SENSOR_ALONG = 4056         # object_y range
GALLERY_COUNT = 48

# Object-gallery plate: the tile grid is chosen to fill the page rather than
# fixed at 6 columns, so a 12-object plate doesn't leave two thirds of it blank.
GALLERY_PLATE_MM = 212.0   # tile area below the section head
GALLERY_WIDTH_MM = 178.0   # A4 minus 16mm margins
GALLERY_GAP_MM = 2.1
GALLERY_META_MM = 5.2      # index + ESD line under each tile

FRAME_PREFIX_RE = re.compile(r"^(.+?)_\d+\.(jpe?g|png)$", re.IGNORECASE)

# All report sections the "Report export" dialog can toggle. Cover, size
# distribution and gallery are always rendered; these are the optional ones.
SECTION_KEYS = ("metadata", "lightness", "saturation", "cleanness", "alignment",
                "focus", "clogging", "stability", "spatial")

# "Objects images" criteria dropdown -> EcoTaxa TSV column (see the mockup).
# Every value is sorted descending (largest / most first).
CRITERIA_COLS = {
    "area": ("object_area", "Area"),
    "equivalent_diameter": ("object_equivalent_diameter", "Equivalent diameter"),
    "major": ("object_major", "Major axis"),
    "minor": ("object_minor", "Minor axis"),
    "perimeter": ("object_perim.", "Perimeter"),
    "circularity": ("object_circ.", "Circularity"),
}
CRITERIA_UNIT = {"area": "px²", "equivalent_diameter": "µm", "major": "px",
                 "minor": "px", "perimeter": "px", "circularity": ""}

# --------------------------------------------------------------------------- #
# Tolerance model
#
# Every check is drawn on a track so the reader sees how much headroom a
# measurement has, not just whether it passed. ``lo``/``hi`` bound the track,
# ``good`` is the acceptable band. All bands are the dashboard's thresholds.
# --------------------------------------------------------------------------- #
TOLERANCE = {
    "lightness":  {"title": "Lightness calibration", "lo": 180, "hi": 255, "good": (220, 240),
                   "limit": "220–240", "lo_label": "180", "hi_label": "255", "unit": "mean lum", "dec": 0},
    "saturation": {"title": "Saturation calibration", "lo": 0, "hi": 15, "good": (0, 5),
                   "limit": "< 5%", "lo_label": "0%", "hi_label": "15%", "unit": "chroma", "dec": 1},
    "cleanness":  {"title": "Cleanness of optical trail", "lo": 0, "hi": 12, "good": (0, 1),
                   "limit": "≤ 1", "lo_label": "0", "hi_label": "12", "unit": "spots", "dec": 0},
    "alignment":  {"title": "Flowcell alignment", "lo": 50, "hi": 100, "good": (85, 100),
                   "limit": "≥ 85%", "lo_label": "50%", "hi_label": "100%", "unit": "uniformity", "dec": 0},
    "focus":      {"title": "Object focus", "lo": 0, "hi": 50, "good": (0, 30),
                   "limit": "< 30%", "lo_label": "0%", "hi_label": "50%", "unit": "blurry", "dec": 1},
    "clogging":   {"title": "Flowcell clogging", "lo": 0, "hi": 30, "good": (0, 10),
                   "limit": "< 10%", "lo_label": "0%", "hi_label": "30%", "unit": "stuck", "dec": 1},
    "stability":  {"title": "Flow stability", "lo": 0, "hi": 150, "good": (0, 100),
                   "limit": "CV < 100%", "lo_label": "0", "hi_label": "150%", "unit": "frame CV", "dec": 0},
}
# Order the conformance panel and the check tables read in.
TOLERANCE_ORDER = ("lightness", "saturation", "cleanness", "alignment",
                   "focus", "clogging", "stability")


def _track(key: str, value: float) -> dict:
    """Position ``value`` and its acceptable band on the 0–100% track for ``key``."""
    s = TOLERANCE[key]
    span = float(s["hi"] - s["lo"]) or 1.0
    place = lambda v: max(0.0, min(100.0, 100.0 * (v - s["lo"]) / span))
    g0, g1 = s["good"]
    return {"pos": place(value), "good_start": place(g0), "good_end": place(g1),
            "clipped": value > s["hi"] or value < s["lo"],
            "limit": s["limit"], "lo_label": s["lo_label"], "hi_label": s["hi_label"]}


# --------------------------------------------------------------------------- #
# Data loading
# --------------------------------------------------------------------------- #
def img_to(path: str, kind: str) -> str:
    """Map an /img/ acquisition path to its /objects/ or /clean/ sibling."""
    return path.replace("/img/", f"/{kind}/").rstrip("/")


def find_tsv(objects_dir: Path) -> Path | None:
    if not objects_dir.is_dir():
        return None
    for f in sorted(objects_dir.iterdir()):
        if f.name.lower().startswith("ecotaxa_") and f.suffix == ".tsv":
            return f
    return None


def read_tsv(tsv_path: Path) -> tuple[list[str], list[dict]]:
    """Return (headers, rows). Skips the EcoTaxa type row ([t]/[f]) and any
    bracketed metadata lines, mirroring the dashboard parsers."""
    with open(tsv_path, newline="", encoding="utf-8", errors="replace") as fh:
        reader = csv.reader(fh, delimiter="\t")
        rows_raw = [r for r in reader if r]
    if not rows_raw:
        return [], []
    headers = [h.strip() for h in rows_raw[0]]
    data = []
    for r in rows_raw[1:]:
        if r and r[0].strip().startswith("["):  # type row or EcoTaxa meta
            continue
        data.append(dict(zip(headers, r)))
    return headers, data


def fnum(v) -> float | None:
    try:
        f = float(str(v).replace(",", "."))
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def frame_of(file_name: str) -> str | None:
    if not file_name:
        return None
    m = FRAME_PREFIX_RE.match(file_name)
    return m.group(1) if m else file_name


# --------------------------------------------------------------------------- #
# Display formatting (precomputed so the templates stay declarative)
# --------------------------------------------------------------------------- #
def fmt_coord(value) -> str:
    v = fnum(value)
    return f"{v:.3f}°" if v is not None else "—"


def fmt_position(lat, lon) -> str:
    la, lo = fnum(lat), fnum(lon)
    if la is None or lo is None:
        return "—"
    ns = "N" if la >= 0 else "S"
    ew = "E" if lo >= 0 else "W"
    return f"{abs(la):.3f}°{ns}, {abs(lo):.3f}°{ew}"


def fmt_sampled(date, time) -> str:
    d = str(date or "").strip()
    t = str(time or "").strip()
    hm = f"{t[:2]}:{t[2:4]}" if len(t) >= 4 and t.isdigit() else t
    return f"{d} {hm}".strip() or "—"


# --------------------------------------------------------------------------- #
# QC computations — ported from the Validation dashboard function nodes
# --------------------------------------------------------------------------- #
def compute_sharpness(rows):
    blurs = sorted(b for b in (fnum(r.get("object_blur_laplacian")) for r in rows) if b is not None)
    total = len(blurs)
    q = lambda p: blurs[int(total * p)] if total else 0
    sharp = sum(1 for v in blurs if v >= SHARP_LAPLACIAN_MIN)
    blurry = sum(1 for v in blurs if v < BLURRY_LAPLACIAN_MAX)
    return {
        "total": total,
        "median": q(0.5), "p10": q(0.1), "p90": q(0.9),
        "sharpPct": 100 * sharp / total if total else 0,
        "blurryPct": 100 * blurry / total if total else 0,
        "values": blurs,
    }


def compute_concentration(rows):
    frames = set()
    for r in rows:
        f = frame_of(r.get("img_file_name", ""))
        if f:
            frames.add(f)
    n = len(frames)
    return {"totalObjects": len(rows), "nFrames": n,
            "perFrame": len(rows) / n if n else 0}


def compute_homogeneity(rows):
    counts = {}
    for r in rows:
        f = frame_of(r.get("img_file_name", ""))
        if f:
            counts[f] = counts.get(f, 0) + 1
    per_frame = [counts[k] for k in sorted(counts)]
    n = len(per_frame)
    mean = sum(per_frame) / n if n else 0
    std = math.sqrt(sum((c - mean) ** 2 for c in per_frame) / n) if n else 0
    return {"nFrames": n, "mean": mean, "std": std,
            "cv": 100 * std / mean if mean else 0, "perFrameCounts": per_frame}


def compute_spatial(rows):
    t1, t2 = SENSOR_ACROSS / 3, 2 * SENSOR_ACROSS / 3
    left = center = right = 0
    points = []
    for r in rows:
        x, y = fnum(r.get("object_x")), fnum(r.get("object_y"))
        if x is None or y is None:
            continue
        if y < t1:
            left += 1
        elif y < t2:
            center += 1
        else:
            right += 1
        points.append((x, y))
    total = left + center + right
    return {
        "total": total, "points": points,
        "leftPct": 100 * left / total if total else 0,
        "centerPct": 100 * center / total if total else 0,
        "rightPct": 100 * right / total if total else 0,
    }


def compute_stuck(rows):
    """Per-frame spatial-bin stuck detection (dashboard STUCK node).

    Returns a per-row boolean list ``stuck_flags`` plus summary counts."""
    bw = math.ceil(SENSOR_ACROSS / STUCK_BIN_PX)
    bh = math.ceil(SENSOR_ALONG / STUCK_BIN_PX)
    bin_frames: dict[int, set] = {}
    objs = []  # (row_index, bin)
    for i, r in enumerate(rows):
        x, y = fnum(r.get("object_x")), fnum(r.get("object_y"))
        if x is None or y is None:
            objs.append((i, None))
            continue
        frame = frame_of(r.get("img_file_name", ""))
        # heatmap x = object_y, heatmap y = object_x (matches AUDIT binning)
        bxi = min(bw - 1, max(0, int(y // STUCK_BIN_PX)))
        byi = min(bh - 1, max(0, int(x // STUCK_BIN_PX)))
        b = byi * bw + bxi
        objs.append((i, b))
        if frame is not None:
            bin_frames.setdefault(b, set()).add(frame)

    stuck_flags = [False] * len(rows)
    stuck_count = 0
    for i, b in objs:
        if b is not None and len(bin_frames.get(b, ())) >= STUCK_MIN_FRAMES:
            stuck_flags[i] = True
            stuck_count += 1
    counted = sum(1 for _, b in objs if b is not None)
    return {
        "stuck_flags": stuck_flags,
        "stuckCount": stuck_count,
        "total": counted,
        "stuckPct": 100 * stuck_count / counted if counted else 0,
    }


def esd_values(rows):
    return [d for d in (fnum(r.get("object_equivalent_diameter")) for r in rows) if d is not None]


# --------------------------------------------------------------------------- #
# Optics / calibration QC — ported from Validation Panels 1-4 (client-side
# canvas analysis of clean/flat_color.jpg). Each returns a dashboard-style dict:
#   {value, measure, state ∈ good|review|alert, label}
# and the pill labels match the dashboard exactly.
# --------------------------------------------------------------------------- #
def _luma(a):
    """Rec.709 luminance of an HxWx3 uint8/float array."""
    return 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]


def _open_rgb(flat_path: Path):
    try:
        return Image.open(flat_path).convert("RGB")
    except (OSError, ValueError):
        return None


def compute_lightness(flat_path: Path):
    """Panel 1 — mean luminance of the flat field (100x100). Good 220-240."""
    im = _open_rgb(flat_path)
    if im is None:
        return None
    a = np.asarray(im.resize((100, 100)), float)
    mean = float(_luma(a).mean())
    state = "good" if 220 <= mean <= 240 else ("alert" if mean < 200 else "review")
    label = {"good": "Optimal", "review": "Suboptimal", "alert": "Critical"}[state]
    return {"label": label, "state": state, "meanLum": mean, "num": mean,
            "value": f"{mean:.0f}", "measure": f"{mean:.0f} / 255 mean luminance"}


def compute_saturation(flat_path: Path):
    """Panel 2 — mean HSV saturation of the flat field (200 wide). Good < 5%."""
    im = _open_rgb(flat_path)
    if im is None:
        return None
    w, h = im.size
    W = 200
    H = max(8, round(W * h / max(1, w)))
    a = np.asarray(im.resize((W, H)), float)
    mx = a.max(axis=2)
    mn = a.min(axis=2)
    sat = np.where(mx == 0, 0.0, (mx - mn) / np.where(mx == 0, 1, mx))
    saturation = float(sat.mean() * 100)
    state = "alert" if saturation > 10 else ("review" if saturation > 5 else "good")
    label = {"good": "Good", "review": "Calibration suggested",
             "alert": "Calibration needed"}[state]
    return {"label": label, "state": state, "saturation": saturation, "num": saturation,
            "value": f"{saturation:.1f}%", "measure": f"{saturation:.1f}% mean chroma"}


def _count_blobs(binary: np.ndarray, y0: int, y1: int, min_size: int = 8) -> int:
    """8-connected components with size >= min_size in rows [y0, y1). Iterative
    flood fill (no scipy on the Pi)."""
    H, W = binary.shape
    visited = np.zeros_like(binary, dtype=bool)
    flagged = 0
    ys, xs = np.nonzero(binary[y0:y1])
    for sy, sx in zip(ys + y0, xs):
        if visited[sy, sx]:
            continue
        stack = [(sy, sx)]
        visited[sy, sx] = True
        size = 0
        while stack:
            cy, cx = stack.pop()
            size += 1
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    if dy == 0 and dx == 0:
                        continue
                    ny, nx = cy + dy, cx + dx
                    if y0 <= ny < y1 and 0 <= nx < W and binary[ny, nx] and not visited[ny, nx]:
                        visited[ny, nx] = True
                        stack.append((ny, nx))
        if size >= min_size:
            flagged += 1
    return flagged


def compute_cleanness(flat_path: Path):
    """Panel 3 — debris on the optical path: count dark spots in the flat field
    (320 wide) that stand out from a 12px-blurred background by >12 luma."""
    im = _open_rgb(flat_path)
    if im is None:
        return None
    w, h = im.size
    W = 320
    H = max(8, round(W * h / max(1, w)))
    im = im.resize((W, H))
    orig = _luma(np.asarray(im, float))
    blur = _luma(np.asarray(im.filter(ImageFilter.GaussianBlur(12)), float))
    margin = int(H * 0.05)
    binary = orig < (blur - 12)
    flagged = _count_blobs(binary, margin, H - margin, min_size=8)
    state = "good" if flagged <= 1 else ("review" if flagged <= 6 else "alert")
    label = {"good": "Good", "review": "Review needed", "alert": "Alert"}[state]
    unit = "spot" if flagged == 1 else "spots"
    return {"label": label, "state": state, "flagged": flagged, "num": float(flagged),
            "value": str(flagged), "measure": f"{flagged} debris {unit}"}


def compute_alignment(flat_path: Path):
    """Panel 4 — flowcell alignment from the edge-vs-centre luminance profile
    (80 rows). Good quality score >= 85."""
    im = _open_rgb(flat_path)
    if im is None:
        return None
    w, h = im.size
    H = 80
    W = max(8, round(H * w / max(1, h)))
    a = np.asarray(im.resize((W, H)), float)
    profile = _luma(a).mean(axis=1)          # per-row mean luminance
    edge = max(1, round(H * 0.10))
    top = float(profile[:edge].mean())
    bottom = float(profile[H - edge:].mean())
    center = float(profile[edge:H - edge].mean())
    diff_l = abs(bottom - center) / center if center > 0 else 0
    diff_r = abs(top - center) / center if center > 0 else 0
    score = 100 - max(diff_l, diff_r) * 400
    max_edge = max(top, bottom)
    if max_edge > 250:
        score -= (max_edge - 250) * 10
    q = max(0, min(100, round(score)))
    state = "good" if q >= 85 else ("review" if q >= 70 else "alert")
    label = {"good": "Aligned", "review": "Slight misalignment",
             "alert": "Misaligned"}[state]
    return {"label": label, "state": state, "qualityScore": q, "num": float(q),
            "value": f"{q}%", "measure": f"{q}% edge uniformity"}


CALIBRATION_SPECS = [
    ("lightness", "Lightness calibration", compute_lightness),
    ("saturation", "Saturation calibration", compute_saturation),
    ("cleanness", "Cleanness of optical trail", compute_cleanness),
    ("alignment", "Flowcell alignment", compute_alignment),
]


def compute_calibration(flat_path: Path, sections: dict):
    """Run only the calibration panels toggled on. Returns a list of rows for
    the template, each {key, title, value, measure, state, label, track}."""
    rows = []
    for key, title, fn in CALIBRATION_SPECS:
        if not sections.get(key):
            continue
        res = fn(flat_path)
        if res is None:
            rows.append({"key": key, "title": title, "value": "—",
                         "measure": "flat_color.jpg unavailable", "unit": "no data",
                         "state": "review", "label": "No data", "track": None})
        else:
            rows.append({"key": key, "title": title, "unit": TOLERANCE[key]["unit"],
                         "track": _track(key, res["num"]), **res})
    return rows


# --------------------------------------------------------------------------- #
# Charts -> base64 PNG
#
# Themed to match the templates: hairline axes, mono tick labels, blue/amber as
# the only ink. Each function returns a base64 PNG data-URI. ``panel=True``
# renders the compact ~3.8x2.65 aspect used by the one-pager's 2x2 grid; the
# default wide aspect is for the full report.
#
# The reporter ships IBM Plex (fonts/) so the charts and the PDF text share one
# typeface; the Pi otherwise only has DejaVu, which we fall back to.
# --------------------------------------------------------------------------- #
def _register_fonts() -> str:
    """Load the bundled TTFs into matplotlib. Returns the mono family to use."""
    if FONTS_DIR.is_dir():
        for ttf in sorted(FONTS_DIR.glob("*.ttf")):
            try:
                font_manager.fontManager.addfont(str(ttf))
            except Exception:  # noqa: BLE001 — a bad font must not kill a report
                pass
    have = {f.name for f in font_manager.fontManager.ttflist}
    return "IBM Plex Mono" if "IBM Plex Mono" in have else "DejaVu Sans Mono"


CHART_INK = "#15181F"
CHART_ACCENT = "#125A9C"
CHART_AMBER = "#C97A04"
CHART_BLURRY = "#C7CCD4"
CHART_LINEMID = "#BBC1CC"
CHART_GRID = "#EEF1F5"
CHART_MUTED = "#6E7785"
CHART_FAINT = "#A6ACB7"
CHART_PAPER = "#FFFFFF"
CHART_MONO = _register_fonts()
CHART_DPI = 200


def _base_style():
    plt.rcParams.update({
        "figure.dpi": CHART_DPI,
        "savefig.dpi": CHART_DPI,
        "font.family": CHART_MONO,
        "font.size": 8.5,
        "text.color": CHART_MUTED,
        "axes.edgecolor": CHART_LINEMID,
        "axes.linewidth": 0.8,
        "axes.facecolor": CHART_PAPER,
        "figure.facecolor": CHART_PAPER,
        "axes.grid": False,
        "xtick.color": CHART_MUTED,
        "ytick.color": CHART_FAINT,
        "xtick.labelsize": 8,
        "ytick.labelsize": 8,
    })


def _strip(ax, left=True):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(CHART_LINEMID)
    if left:
        ax.spines["left"].set_visible(False)
    ax.tick_params(length=3, width=0.8, colors=CHART_MUTED)


def _hgrid(ax, ys):
    for i, y in enumerate(ys):
        ax.axhline(y, color=(CHART_LINEMID if i == 0 else CHART_GRID),
                   lw=(1.0 if i == 0 else 0.8), zorder=0)


def _to_datauri(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", pad_inches=0.06,
                facecolor=CHART_PAPER)
    plt.close(fig)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _mono_label(ax, text, x=0.0, y=-0.20, size=7.5, color=CHART_FAINT):
    ax.text(x, y, text, transform=ax.transAxes, ha="left", va="top",
            fontsize=size, color=color, family=CHART_MONO)


def _yticks(ymax, steps):
    """Pick from ``steps`` the tick values that fit under ymax (deduped)."""
    ticks = sorted({0.0} | {t for t in steps if t <= ymax})
    return ticks


def chart_esd(esds, stuck_flags, median, panel=False):
    if not esds:
        return None
    _base_style()
    esds = np.asarray(esds, float)
    stuck = np.asarray(stuck_flags, bool)
    lo = max(1.0, min(20.0, float(esds.min())))
    hi = max(500.0, float(esds.max()))
    edges = np.logspace(math.log10(lo), math.log10(hi), 23)

    fig, ax = plt.subplots(figsize=(3.8, 2.65) if panel else (7.6, 2.05))
    cf, _ = np.histogram(esds[~stuck], bins=edges)
    cs, _ = np.histogram(esds[stuck], bins=edges)

    ax.bar(edges[:-1], cf, width=np.diff(edges), align="edge",
           color=CHART_ACCENT, linewidth=0, zorder=3)
    ax.bar(edges[:-1], cs, width=np.diff(edges), align="edge", bottom=cf,
           color=CHART_AMBER, linewidth=0, zorder=3)

    ax.set_xscale("log")
    ax.set_xlim(lo, hi)
    ymax = float((cf + cs).max()) * 1.10 if (cf + cs).size else 1.0
    ax.set_ylim(0, ymax)
    _strip(ax)
    yt = _yticks(ymax, [round(ymax / 3, -2), round(2 * ymax / 3, -2)])
    ax.set_yticks(yt)
    _hgrid(ax, yt)

    ticks = [t for t in (20, 30, 50, 100, 200, 500) if lo <= t <= hi]
    ax.xaxis.set_major_locator(FixedLocator(ticks))
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{int(v)}"))
    ax.minorticks_off()

    ax.axvline(median, color=CHART_INK, lw=1.0, ls=(0, (3, 3)), zorder=4)
    ax.text(median * 1.03, ymax * 0.97, f"median {median:.0f} µm",
            color=CHART_INK, fontsize=8, va="top", ha="left", family=CHART_MONO)

    if stuck.any():
        ax.scatter([], [], marker="s", s=42, color=CHART_ACCENT, label="flowing")
        ax.scatter([], [], marker="s", s=42, color=CHART_AMBER, label="stuck")
        ax.legend(loc="upper right", frameon=False, handletextpad=0.5,
                  labelcolor=CHART_MUTED, fontsize=8, borderaxespad=0.2)

    _mono_label(ax, "EQUIVALENT SPHERICAL DIAMETER  ·  µm")
    return _to_datauri(fig)


def chart_sharpness(values, median, cutoff, panel=False, duo=False):
    if not values:
        return None
    _base_style()
    v = np.asarray(values, float)
    # Data-driven x-axis: the focus measure is a scale/contrast-invariant ratio
    # (~0.04–1.4), so a fixed range would squash everything against zero. Cap at
    # the 99.5th percentile and always keep the cutoffs comfortably in view.
    hi = float(np.quantile(v, 0.995)) if v.size else 1.0
    hi = max(hi, cutoff * 3, SHARP_LAPLACIAN_MIN * 1.5, 0.3)
    edges = np.linspace(0, hi, 31)
    counts, _ = np.histogram(np.clip(v, 0, hi), bins=edges)
    centers = (edges[:-1] + edges[1:]) / 2
    colors = np.where(centers < cutoff, CHART_BLURRY, CHART_ACCENT)

    fig, ax = plt.subplots(figsize=(3.8, 2.65) if panel else ((4.6, 2.51) if duo else (7.6, 2.8)))
    ax.bar(edges[:-1], counts, width=np.diff(edges) * 0.94, align="edge",
           color=colors, linewidth=0, zorder=3)

    ax.set_xlim(0, hi)
    ymax = float(counts.max()) * 1.12 if counts.size else 1.0
    ax.set_ylim(0, ymax)
    _strip(ax)
    yt = _yticks(ymax, [round(ymax / 2, -2)])
    ax.set_yticks(yt)
    _hgrid(ax, yt)
    xt = np.round(np.linspace(0, hi, 4 if duo else 6), 2)
    ax.set_xticks(xt)
    ax.xaxis.set_major_formatter(FuncFormatter(lambda x, _: f"{x:.2f}"))
    lab = 9.5 if duo else 8
    ax.tick_params(labelsize=lab)

    ax.axvline(cutoff, color=CHART_INK, lw=1.0, ls=(0, (3, 3)), zorder=4)
    if not duo:  # no room beside the legend in the narrow column; the caption says it
        ax.text(cutoff + hi * 0.01, ymax * 0.97, "blurry cutoff", color=CHART_INK,
                fontsize=lab, va="top", ha="left", family=CHART_MONO)
    ax.axvline(median, color=CHART_LINEMID, lw=1.0, zorder=2)
    flip = median > hi * 0.55  # keep the label inside the axes
    ax.text(median + (-1 if flip else 1) * hi * 0.015, ymax * (0.97 if duo else 0.86),
            f"median {median:.2f}", color=CHART_MUTED, fontsize=lab,
            va="top", ha="right" if flip else "left", family=CHART_MONO)

    ax.scatter([], [], marker="s", s=42, color=CHART_BLURRY, label="blurry")
    ax.scatter([], [], marker="s", s=42, color=CHART_ACCENT, label="sharp")
    # The tall in-focus bar sits at the right edge in the wide chart, so the
    # legend goes upper-center there; in the duo column the peak is left of centre.
    ax.legend(loc="upper right" if duo else "upper center", ncol=1 if duo else 2,
              frameon=False, handletextpad=0.5, labelcolor=CHART_MUTED,
              fontsize=lab, borderaxespad=0.2)

    _mono_label(ax, "FOCUS MEASURE" if duo else "FOCUS MEASURE  ·  SHARPNESS RATIO",
                size=(9 if duo else 7.5))
    return _to_datauri(fig)


def chart_heatmap(points, thirds, panel=False, gamma=0.72):
    """``points`` are (object_x, object_y); thirds = (leftPct, centerPct,
    rightPct). Matches the dashboard SPATIAL convention: object_y is the
    *across*-flowcell axis (short, 0..ACROSS) and carries the left/center/right
    thirds — drawn horizontally; object_x is the *along*-flowcell axis (the long
    one) — drawn vertically, so the plot is portrait like the physical flowcell."""
    if not points:
        return None
    _base_style()
    pts = np.asarray(points, float)
    x, y = pts[:, 1], pts[:, 0]  # x = object_y (across, thirds); y = object_x (along, long)
    if x.min() == x.max() or y.min() == y.max():
        return None

    cmap = LinearSegmentedColormap.from_list(
        "psblue", ["#FBFCFE", "#9CC3E6", "#16548C"])

    # finer binning on the long (along / vertical) axis
    H, _, _ = np.histogram2d(
        x, y, bins=(24, 32),
        range=[[x.min(), x.max()], [y.min(), y.max()]])
    k = np.array([[0.5, 1, 0.5], [1, 2, 1], [0.5, 1, 0.5]]); k /= k.sum()
    Hs = np.copy(H)
    Hs[1:-1, 1:-1] = sum(
        k[a + 1, b + 1] * H[1 + a:H.shape[0] - 1 + a, 1 + b:H.shape[1] - 1 + b]
        for a in (-1, 0, 1) for b in (-1, 0, 1))

    lo = Hs.min(); p96 = np.quantile(Hs, 0.96)
    norm = np.clip((Hs - lo) / max(1e-9, (p96 - lo)), 0, 1) ** gamma

    # portrait figure: the long (vertical) axis is taller than the short one
    fig, ax = plt.subplots(figsize=(2.6, 3.2) if panel else (4.0, 4.4))
    im = ax.imshow(norm.T, origin="lower", aspect="auto", cmap=cmap,
                   interpolation="nearest")
    ax.set_xticks([]); ax.set_yticks([])
    for s in ax.spines.values():
        s.set_color(CHART_LINEMID); s.set_linewidth(0.8)

    if panel:
        left, center, right = thirds
        for frac, txt in zip((1 / 6, 1 / 2, 5 / 6),
                             (f"LEFT {left:.0f}%", f"CENTER {center:.0f}%",
                              f"RIGHT {right:.0f}%")):
            ax.text(frac, -0.05, txt, transform=ax.transAxes, ha="center",
                    va="top", fontsize=8, color=CHART_MUTED, family=CHART_MONO)
        _mono_label(ax, "FLOWCELL  ·  CAMERA ORIENTATION", y=-0.12)
    else:
        _mono_label(ax, "ACROSS FLOWCELL", y=-0.035, size=11)

    cb = fig.colorbar(im, ax=ax, fraction=0.035, pad=0.03)
    cb.outline.set_edgecolor(CHART_LINEMID); cb.outline.set_linewidth(0.8)
    cb.set_ticks([0, 1]); cb.set_ticklabels(["LOW", "HIGH"])
    cb.ax.tick_params(length=0, labelsize=(7.5 if panel else 10), colors=CHART_MUTED)
    if panel:
        cb.set_label("DENSITY", color=CHART_FAINT, fontsize=7, family=CHART_MONO, labelpad=6)
    return _to_datauri(fig)


def chart_concentration(per_frame_counts, mean, panel=True):
    if not per_frame_counts:
        return None
    _base_style()
    v = np.asarray(per_frame_counts, float)
    n = len(v)
    fig, ax = plt.subplots(figsize=(3.8, 2.65) if panel else (7.6, 2.8))
    xs = np.arange(n)
    ax.fill_between(xs, v, color=CHART_ACCENT, alpha=0.12, linewidth=0)
    ax.plot(xs, v, color=CHART_ACCENT, lw=1.0)

    ymax = float(v.max()) * 1.10 if v.size else 1.0
    ax.set_xlim(0, max(1, n - 1)); ax.set_ylim(0, ymax)
    _strip(ax)
    yt = _yticks(ymax, [15, 30, 45, 60])
    ax.set_yticks(yt); _hgrid(ax, yt)
    ax.set_xticks([t for t in (0, 100, 200, 300) if t <= n])

    ax.axhline(mean, color=CHART_AMBER, lw=1.0, ls=(0, (4, 3)), zorder=4)
    ax.text(n - 1, mean + ymax * 0.04, f"mean {mean:.1f}", color=CHART_AMBER,
            fontsize=8, va="bottom", ha="right", family=CHART_MONO)
    _mono_label(ax, f"OBJECTS PER FRAME  ·  N = {n}")
    return _to_datauri(fig)


# --------------------------------------------------------------------------- #
# Images -> base64
# --------------------------------------------------------------------------- #
def img_b64(path: Path) -> str | None:
    try:
        data = path.read_bytes()
    except OSError:
        return None
    mime = "image/jpeg" if path.suffix.lower() in (".jpg", ".jpeg") else "image/png"
    return f"data:{mime};base64," + base64.b64encode(data).decode()


def gallery_layout(n: int) -> tuple[int, float]:
    """Columns and tile height (mm) giving the squarest tiles that fill a plate.

    Falls back to a dense 8-column grid when the selection is too large for one
    page; the plate then flows across pages at a fixed tile size."""
    best = None
    for cols in range(2, 9):
        rows = math.ceil(n / cols)
        tile_w = (GALLERY_WIDTH_MM - (cols - 1) * GALLERY_GAP_MM) / cols
        h = (GALLERY_PLATE_MM - rows * GALLERY_META_MM - (rows - 1) * GALLERY_GAP_MM) / rows
        if h < 11:                       # this many rows can't share one page
            continue
        h = min(h, tile_w * 1.35, 60.0)  # never let a sparse plate become posters
        used = rows * (h + GALLERY_META_MM) + (rows - 1) * GALLERY_GAP_MM
        # Fill the plate first, squareness second.
        score = (GALLERY_PLATE_MM - used) + 2.0 * abs(h - tile_w)
        if best is None or score < best[0]:
            best = (score, cols, h)
    if best is None:
        return 8, 12.0
    return best[1], round(best[2], 1)


def gallery_tiles(rows, objects_dir: Path, criteria="equivalent_diameter",
                  mode="top", count=GALLERY_COUNT):
    """Pick ROI thumbnails for the plate.

    ``criteria`` selects the ranking column (see CRITERIA_COLS); ``mode`` is
    "top" (largest by criteria) or "random"; ``count`` caps the tiles. Every
    tile still shows its ESD label so the gallery stays comparable."""
    col, _ = CRITERIA_COLS.get(criteria, CRITERIA_COLS["equivalent_diameter"])
    try:
        count = max(1, min(200, int(count)))
    except (TypeError, ValueError):
        count = GALLERY_COUNT

    enriched = []
    for r in rows:
        oid = r.get("object_id")
        val = fnum(r.get(col))
        esd = fnum(r.get("object_equivalent_diameter"))
        if oid is None or val is None:
            continue
        enriched.append((val, esd, oid))

    if mode == "random":
        import random
        rng = random.Random(1234)  # deterministic so re-runs are reproducible
        rng.shuffle(enriched)
        chosen = enriched[:count]
        chosen.sort(key=lambda t: t[0], reverse=True)  # still present largest-first
    else:
        enriched.sort(key=lambda t: t[0], reverse=True)
        chosen = enriched[:count]

    tiles = []
    for val, esd, oid in chosen:
        b64 = img_b64(objects_dir / f"{oid}.jpg")
        if b64:
            tiles.append({"img": b64,
                          "esd": f"{esd:.0f} µm" if esd is not None else "—",
                          "id": oid})
    return tiles


# --------------------------------------------------------------------------- #
# Report assembly
# --------------------------------------------------------------------------- #
def load_hardware():
    try:
        return json.loads(HARDWARE_JSON.read_text())
    except OSError:
        return {}


def _load_acquisition(acquisition_path: str):
    """Read one acquisition and compute every stat the report can draw on.

    Returns a dict of raw results + a ``common`` block of display-ready fields
    shared by every render path. Callers decide which sections / charts / gallery
    to build from it, so the heavy TSV + image work happens exactly once."""
    img_dir = Path(acquisition_path.rstrip("/"))
    objects_dir = Path(img_to(str(img_dir), "objects"))
    clean_dir = Path(img_to(str(img_dir), "clean"))

    metadata = json.loads((img_dir / "metadata.json").read_text())
    tsv = find_tsv(objects_dir)
    if tsv is None:
        raise FileNotFoundError(f"No ecotaxa_*.tsv in {objects_dir}")
    headers, rows = read_tsv(tsv)
    if not rows:
        raise ValueError("TSV has no object rows")

    sharp = compute_sharpness(rows)
    conc = compute_concentration(rows)
    homo = compute_homogeneity(rows)
    spatial = compute_spatial(rows)
    stuck = compute_stuck(rows)
    esds = esd_values(rows)

    def pct(vals, p):
        return statistics.quantiles(vals, n=100)[p - 1] if len(vals) > 1 else (vals[0] if vals else 0)

    hardware = load_hardware()
    instrument = f"PlanktoScope {hardware.get('hat_type', '')} v{hardware.get('hat_version', '')}".strip()
    stats = {
        "total": len(rows),
        "esd_min": min(esds) if esds else 0,
        "esd_p10": pct(esds, 10),
        "esd_median": statistics.median(esds) if esds else 0,
        "esd_p90": pct(esds, 90),
        "esd_max": max(esds) if esds else 0,
        "flowingPct": 100 - stuck["stuckPct"],
        "stuckPct": stuck["stuckPct"],
        "perFrame": conc["perFrame"],
    }

    # Aligned ESD / stuck arrays for the histogram (drop rows with no ESD).
    esd_pairs = [(fnum(r.get("object_equivalent_diameter")), stuck["stuck_flags"][i])
                 for i, r in enumerate(rows)]
    esd_pairs = [(e, s) for e, s in esd_pairs if e is not None]

    common = {
        "meta": metadata,
        "serial": metadata.get("acq_instrument_serial_number", "—"),
        "instrument": instrument,
        "instrument_short": instrument.replace("PlanktoScope ", "").strip() or instrument,
        "brand_logo": img_b64(HERE / "logo.png"),
        "position": fmt_position(metadata.get("object_lat"), metadata.get("object_lon")),
        "lat_disp": fmt_coord(metadata.get("object_lat")),
        "lon_disp": fmt_coord(metadata.get("object_lon")),
        "sampled": fmt_sampled(metadata.get("object_date"), metadata.get("object_time")),
        "stats": stats,
        "sharp": sharp, "conc": conc, "homo": homo, "spatial": spatial, "stuck": stuck,
        "flat_field": img_b64(clean_dir / "flat_color.jpg"),
    }
    name = "_".join(filter(None, [
        metadata.get("sample_project"), metadata.get("sample_id"),
        metadata.get("acq_id")])) or img_dir.name

    return {
        "img_dir": img_dir, "objects_dir": objects_dir, "clean_dir": clean_dir,
        "metadata": metadata, "rows": rows,
        "sharp": sharp, "conc": conc, "homo": homo, "spatial": spatial,
        "stuck": stuck, "stats": stats,
        "esd_arr": [e for e, _ in esd_pairs],
        "esd_stuck": [s for _, s in esd_pairs],
        "thirds": (spatial["leftPct"], spatial["centerPct"], spatial["rightPct"]),
        "common": common, "name": name,
    }


def normalize_sections(raw):
    """Coerce the dialog's section toggles. Absent dict = every section on."""
    if not raw:
        return {k: True for k in SECTION_KEYS}
    return {k: bool(raw.get(k, False)) for k in SECTION_KEYS}


def normalize_gallery(raw):
    """Coerce the dialog's 'Objects images' options."""
    raw = raw or {}
    mode = "random" if str(raw.get("mode", "top")).lower() == "random" else "top"
    try:
        count = int(raw.get("count", GALLERY_COUNT))
    except (TypeError, ValueError):
        count = GALLERY_COUNT
    count = max(1, min(200, count))
    crit = str(raw.get("criteria", "equivalent_diameter")).lower()
    if crit not in CRITERIA_COLS:
        crit = "equivalent_diameter"
    return {"mode": mode, "count": count, "criteria": crit}


def build_qc_rows(sharp, stuck, homo, sections):
    """QC rows for the toggled focus / clogging / stability panels only.

    Shaped like the calibration rows (key/title/value/measure/state/track) so
    both feed the same table and the same cover conformance panel."""
    b, s, cv = sharp["blurryPct"], stuck["stuckPct"], homo["cv"]
    spec = [
        ("focus", b, f"{b:.1f}%", f"{b:.1f}% of objects blurry", 30),
        ("clogging", s, f"{s:.1f}%", f"{s:.1f}% of objects stuck", 10),
        ("stability", cv, f"{cv:.0f}%", f"CV {cv:.0f}% across frames", 100),
    ]
    rows = []
    for key, num, value, measure, ceiling in spec:
        if not sections.get(key):
            continue
        ok = num < ceiling
        rows.append({
            "key": key, "title": TOLERANCE[key]["title"], "num": num,
            "value": value, "measure": measure, "pass": ok,
            "unit": TOLERANCE[key]["unit"], "limit": TOLERANCE[key]["limit"],
            "state": "good" if ok else "alert",
            "label": "Pass" if ok else "Fail",
            "track": _track(key, num),
        })
    return rows


def _fmt_range(values, dec: int) -> str:
    """A readout spanning one or many acquisitions, at the quantity's precision."""
    lo, hi = min(values), max(values)
    if abs(hi - lo) < (0.05 if dec else 0.5):
        return f"{lo:.{dec}f}"
    return f"{lo:.{dec}f}\u2013{hi:.{dec}f}"


def build_conformance(acqs, sections):
    """Cover panel: one track per evaluated check, one tick per acquisition.

    With several acquisitions the ticks share a track, so the spread across a
    project reads at a glance — tight clusters mean a stable instrument."""
    rows = []
    for key in TOLERANCE_ORDER:
        if not sections.get(key):
            continue
        ticks, values, singles = [], [], []
        for i, a in enumerate(acqs, 1):
            src = next((c for c in a["calibration"] + a["qc"] if c.get("key") == key), None)
            if not src or not src.get("track"):
                continue
            ticks.append({"pos": src["track"]["pos"], "state": src["state"], "idx": i})
            values.append(src["num"])
            singles.append(src["value"])
        if not ticks:
            continue
        # Alternate the tick labels above/below the track where acquisitions
        # cluster, so their numbers stay readable.
        ticks.sort(key=lambda t: t["pos"])
        prev, low = -99.0, False
        for t in ticks:
            low = (not low) if (t["pos"] - prev) < 6.0 else False
            t["low"] = low
            prev = t["pos"]

        s = TOLERANCE[key]
        rows.append({
            "key": key, "title": s["title"], "limit": s["limit"], "unit": s["unit"],
            "lo_label": s["lo_label"], "hi_label": s["hi_label"],
            "good_start": _track(key, s["good"][0])["pos"],
            "good_end": _track(key, s["good"][1])["pos"],
            "ticks": ticks, "numbered": len(ticks) > 1 and len(ticks) <= 6,
            "state": ("alert" if any(t["state"] == "alert" for t in ticks)
                      else "review" if any(t["state"] == "review" for t in ticks) else "good"),
            "readout": _fmt_range(values, s["dec"]) if len(values) > 1 else singles[0],
        })
    return rows


def build_qc_table(sharp, stuck, conc, homo):
    """Legacy full QC table (green-pass / red-fail) used by the single-acq path."""
    return [
        {"label": "Focus quality",
         "value": f"{sharp['blurryPct']:.1f}% blurry",
         "limit": "< 30% blurry", "pass": sharp["blurryPct"] < 30},
        {"label": "Flowcell clogging (stuck)",
         "value": f"{stuck['stuckPct']:.1f}% stuck",
         "limit": "< 10% stuck", "pass": stuck["stuckPct"] < 10},
        {"label": "Concentration",
         "value": f"{conc['perFrame']:.2f} obj/frame",
         "limit": "1–50 obj/frame", "pass": 1 <= conc["perFrame"] <= 50},
        {"label": "Spatial homogeneity",
         "value": f"CV {homo['cv']:.0f}%",
         "limit": "CV < 100%", "pass": homo["cv"] < 100},
    ]


def build_context(acquisition_path: str):
    """Legacy single-acquisition context (full + one-pager). Unchanged output.

    Returns ``(full_ctx, panel_ctx, name)``. Still used by the backward-compatible
    ``acquisition_path`` MQTT payload"""
    L = _load_acquisition(acquisition_path)
    sharp, conc, homo, spatial, stuck = L["sharp"], L["conc"], L["homo"], L["spatial"], L["stuck"]
    qc = build_qc_table(sharp, stuck, conc, homo)
    base = {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        **L["common"],
        "qc": qc,
        "qc_pass": all(row["pass"] for row in qc),
        "gallery": gallery_tiles(L["rows"], L["objects_dir"]),
        "gallery_count": GALLERY_COUNT,
    }
    full_ctx = {
        **base,
        "chart_esd": chart_esd(L["esd_arr"], L["esd_stuck"], L["stats"]["esd_median"]),
        "chart_sharpness": chart_sharpness(sharp["values"], sharp["median"], BLURRY_LAPLACIAN_MAX),
        "chart_heatmap": chart_heatmap(spatial["points"], L["thirds"]),
    }
    panel_ctx = {
        **base,
        "chart_esd": chart_esd(L["esd_arr"], L["esd_stuck"], L["stats"]["esd_median"], panel=True),
        "chart_sharpness": chart_sharpness(sharp["values"], sharp["median"], BLURRY_LAPLACIAN_MAX, panel=True),
        "chart_heatmap": chart_heatmap(spatial["points"], L["thirds"], panel=True),
        "chart_concentration": chart_concentration(homo["perFrameCounts"], conc["perFrame"]),
    }
    return full_ctx, panel_ctx, L["name"]


def build_acq_context(acquisition_path: str, sections: dict, gallery_opts: dict):
    """Per-acquisition context for the combined 'Report export' template. Only
    the toggled sections' heavy work (calibration, charts) is done."""
    L = _load_acquisition(acquisition_path)
    sharp, homo, spatial, stuck = L["sharp"], L["homo"], L["spatial"], L["stuck"]

    calibration = compute_calibration(L["clean_dir"] / "flat_color.jpg", sections)
    qc_rows = build_qc_rows(sharp, stuck, homo, sections)

    cal_alert = any(r["state"] == "alert" for r in calibration)
    qc_fail = any(not r["pass"] for r in qc_rows)
    acq_pass = not cal_alert and not qc_fail
    issues = sum(r["state"] == "alert" for r in calibration) + sum(not r["pass"] for r in qc_rows)
    evaluated = len(calibration) + len(qc_rows)

    show_calibration = any(sections.get(k) for k in ("lightness", "saturation", "cleanness", "alignment"))
    show_qc = bool(qc_rows)

    crit_col, crit_label = CRITERIA_COLS[gallery_opts["criteria"]]
    gallery = gallery_tiles(L["rows"], L["objects_dir"], gallery_opts["criteria"],
                            gallery_opts["mode"], gallery_opts["count"])
    gallery_cols, gallery_tile_mm = gallery_layout(len(gallery))

    ctx = {
        **L["common"],
        "sections": sections,
        "calibration": calibration,
        "show_calibration": show_calibration,
        "qc": qc_rows,
        "show_qc": show_qc,
        "acq_pass": acq_pass,
        "issues": issues,
        "evaluated": evaluated,
        "gallery": gallery,
        "gallery_opts": gallery_opts,
        "gallery_criteria_label": crit_label,
        "gallery_cols": gallery_cols,
        "gallery_tile_mm": gallery_tile_mm,
        # size distribution is always shown; focus/spatial charts are gated
        "chart_esd": chart_esd(L["esd_arr"], L["esd_stuck"], L["stats"]["esd_median"]),
        "chart_sharpness": (chart_sharpness(sharp["values"], sharp["median"], BLURRY_LAPLACIAN_MAX, duo=True)
                            if sections.get("focus") else None),
        "chart_heatmap": (chart_heatmap(spatial["points"], L["thirds"])
                          if sections.get("spatial") else None),
        "name": L["name"],
    }
    return ctx


def build_report(acquisition_path: str) -> dict:
    """Render both PDFs (full + one-pager) and return their paths. (Legacy.)"""
    full_ctx, panel_ctx, name = build_context(acquisition_path)

    env = Environment(loader=FileSystemLoader(str(HERE)),
                      autoescape=select_autoescape(["html"]))
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    out = REPORTS_DIR / f"{name}_report.pdf"
    HTML(string=env.get_template("template.html").render(**full_ctx),
         base_url=str(HERE)).write_pdf(str(out))

    onepage = REPORTS_DIR / f"{name}_report_onepage.pdf"
    HTML(string=env.get_template("template_onepage.html").render(**panel_ctx),
         base_url=str(HERE)).write_pdf(str(onepage))

    return {"full": out, "onepage": onepage}


def build_combined_report(acquisition_paths, sections=None, gallery_opts=None) -> dict:
    """Render ONE full PDF covering all selected acquisitions with the chosen
    sections + gallery options. Returns {'full': Path}."""
    sections = normalize_sections(sections)
    gallery_opts = normalize_gallery(gallery_opts)

    acqs = []
    errors = []
    for p in acquisition_paths:
        try:
            acqs.append(build_acq_context(p, sections, gallery_opts))
        except Exception as exc:  # noqa: BLE001 — skip a bad acq, keep the rest
            traceback.print_exc()
            errors.append(f"{Path(p).name}: {exc}")
    if not acqs:
        raise ValueError("No acquisition could be loaded: " + "; ".join(errors) if errors
                         else "No acquisitions selected")

    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    doc = {
        "generated": generated,
        "sections": sections,
        "gallery_opts": gallery_opts,
        "acqs": acqs,
        "multi": len(acqs) > 1,
        "n_acq": len(acqs),
        # cover / running fields taken from the first acquisition
        "brand_logo": acqs[0]["brand_logo"],
        "serial": acqs[0]["serial"],
        "instrument_short": acqs[0]["instrument_short"],
        "cover_project": acqs[0]["meta"].get("sample_project") or "—",
        "total_objects": sum(a["stats"]["total"] for a in acqs),
        "all_pass": all(a["acq_pass"] for a in acqs),
        "total_issues": sum(a["issues"] for a in acqs),
        "conformance": build_conformance(acqs, sections),
        "errors": errors,
    }

    env = Environment(loader=FileSystemLoader(str(HERE)),
                      autoescape=select_autoescape(["html"]))
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    if len(acqs) == 1:
        stem = acqs[0]["name"]
    else:
        proj = re.sub(r"[^A-Za-z0-9]+", "-", str(acqs[0]["meta"].get("sample_project") or "report")).strip("-")
        stem = f"{proj}_{len(acqs)}acq"
    out = REPORTS_DIR / f"{stem}_report.pdf"
    HTML(string=env.get_template("template_combined.html").render(**doc),
         base_url=str(HERE)).write_pdf(str(out))
    return {"full": out}


# --------------------------------------------------------------------------- #
# MQTT (asyncio / aiomqtt)
# --------------------------------------------------------------------------- #
async def publish(client: "aiomqtt.Client", payload: dict) -> None:
    await client.publish(TOPIC_OUT, json.dumps(payload))
    print(f"[reporter] -> {TOPIC_OUT}: {payload}", flush=True)


async def _handle_generate(client: "aiomqtt.Client", data: dict) -> None:
    """Dispatch a generate request. Two payload shapes are accepted:

    NEW  {action, acquisition_paths:[...], sections:{...}, gallery:{...}}
         -> one combined full PDF (the "Report export" dialog).
    LEGACY {action, acquisition_path:"..."}
         -> the original full + one-pager pair (per-row button).

    PDF generation is CPU-bound (matplotlib + WeasyPrint), so it runs in a
    worker thread via ``asyncio.to_thread`` to keep the MQTT client responsive.
    Messages are awaited one at a time, which serialises generation — matplotlib's
    pyplot state is not safe to drive from concurrent threads."""
    paths = data.get("acquisition_paths")
    if isinstance(paths, list) and paths:
        label = f"{len(paths)} acquisition(s)"
        await publish(client, {"status": "generating", "count": len(paths),
                               "acquisition_paths": paths})
        try:
            res = await asyncio.to_thread(
                build_combined_report, paths, data.get("sections"), data.get("gallery"))
            full = res["full"]
            await publish(client, {"status": "done", "acquisition_paths": paths,
                                   "path": str(full), "filename": full.name,
                                   "url": f"/api/files/reports/{full.name}",
                                   "filename_full": full.name,
                                   "url_full": f"/api/files/reports/{full.name}"})
            print(f"[reporter] wrote {full} ({label})", flush=True)
        except Exception as exc:  # noqa: BLE001 — report any failure to the UI
            traceback.print_exc()
            await publish(client, {"status": "error", "acquisition_paths": paths,
                                   "error": str(exc)})
        return

    acq = data.get("acquisition_path")
    if not acq:
        return
    print(f"[reporter] generating report for {acq}", flush=True)
    await publish(client, {"status": "generating", "acquisition_path": acq})
    try:
        res = await asyncio.to_thread(build_report, acq)
        full, onep = res["full"], res["onepage"]
        await publish(client, {"status": "done", "acquisition_path": acq,
                               # legacy fields (= full report) kept for compatibility
                               "path": str(full), "filename": full.name,
                               "url": f"/api/files/reports/{full.name}",
                               # both formats, so the dashboard can offer a choice
                               "filename_full": full.name,
                               "url_full": f"/api/files/reports/{full.name}",
                               "filename_onepage": onep.name,
                               "url_onepage": f"/api/files/reports/{onep.name}"})
        print(f"[reporter] wrote {full} and {onep}", flush=True)
    except Exception as exc:  # noqa: BLE001 — report any failure to the UI
        traceback.print_exc()
        await publish(client, {"status": "error", "acquisition_path": acq, "error": str(exc)})


async def _handle_message(client: "aiomqtt.Client", message: "aiomqtt.Message") -> None:
    try:
        data = json.loads(message.payload.decode())
    except (ValueError, UnicodeDecodeError):
        print(f"[reporter] bad payload: {message.payload!r}", flush=True)
        return
    if not isinstance(data, dict) or data.get("action") != "generate":
        return
    await _handle_generate(client, data)


async def start() -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    async with aiomqtt.Client(hostname=MQTT_HOST, port=MQTT_PORT) as client:
        await client.subscribe(TOPIC_IN)
        print(f"[reporter] connected {MQTT_HOST}:{MQTT_PORT}, subscribed {TOPIC_IN}", flush=True)
        async for message in client.messages:
            await _handle_message(client, message)


def main() -> None:
    if "--once" in sys.argv:  # local test: legacy single-acq (full + one-pager)
        res = build_report(sys.argv[sys.argv.index("--once") + 1])
        print(f"wrote {res['full']} and {res['onepage']}")
        return
    if "--payload" in sys.argv:  # local test: exact dialog payload (JSON), no MQTT
        data = json.loads(sys.argv[sys.argv.index("--payload") + 1])
        res = build_combined_report(data.get("acquisition_paths") or [data["acquisition_path"]],
                                    data.get("sections"), data.get("gallery"))
        print(f"wrote {res['full']}")
        return
    asyncio.run(start())


if __name__ == "__main__":
    main()
