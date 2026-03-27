#!/usr/bin/env python3
"""
analyze_acquisition.py - Post-acquisition analysis for PlanktoScope Live Segmentation

Analyzes completed acquisitions to provide:
- Object size distributions
- Detection rate over time
- Quality metrics (blur scores, morphology)
- Comparison between live and batch segmentation

Usage:
    python3 analyze_acquisition.py /path/to/objects/date/sample/acq_folder
    python3 analyze_acquisition.py --latest          # Analyze most recent acquisition
    python3 analyze_acquisition.py --compare FOLDER  # Compare with batch segmentation
"""

import argparse
import csv
import json
import os
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# Configuration
OBJECTS_BASE = "/home/pi/data/objects"
IMG_BASE = "/home/pi/data/img"

# ANSI colors
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[2m'


def find_latest_acquisition():
    """Find the most recently modified acquisition directory."""
    latest_time = 0
    latest_dir = None

    for date_dir in sorted(os.listdir(OBJECTS_BASE), reverse=True):
        date_path = os.path.join(OBJECTS_BASE, date_dir)
        if not os.path.isdir(date_path):
            continue

        for sample_dir in os.listdir(date_path):
            sample_path = os.path.join(date_path, sample_dir)
            if not os.path.isdir(sample_path):
                continue

            for acq_dir in os.listdir(sample_path):
                acq_path = os.path.join(sample_path, acq_dir)
                if not os.path.isdir(acq_path):
                    continue

                mtime = os.path.getmtime(acq_path)
                if mtime > latest_time:
                    latest_time = mtime
                    latest_dir = acq_path

    return latest_dir


def find_tsv_file(acq_dir):
    """Find the EcoTaxa TSV file in an acquisition directory."""
    folder_name = os.path.basename(acq_dir)

    # Try different naming patterns
    patterns = [
        f"ecotaxa_{folder_name}.tsv",
        f"ecotaxa_export.tsv",
    ]

    for pattern in patterns:
        tsv_path = os.path.join(acq_dir, pattern)
        if os.path.exists(tsv_path):
            return tsv_path

    # Search for any TSV file
    for f in os.listdir(acq_dir):
        if f.endswith('.tsv'):
            return os.path.join(acq_dir, f)

    return None


def parse_tsv(tsv_path):
    """Parse EcoTaxa TSV file and return list of objects."""
    objects = []

    try:
        with open(tsv_path, 'r') as f:
            reader = csv.DictReader(f, delimiter='\t')

            # Skip the type indicator row if present
            for row in reader:
                # Skip type indicator row
                if row.get('object_id', '').startswith('['):
                    continue

                # Parse numeric fields
                obj = {}
                for key, value in row.items():
                    try:
                        # Try to convert to float
                        obj[key] = float(value) if value and '.' in value else int(value) if value and value.lstrip('-').isdigit() else value
                    except (ValueError, TypeError):
                        obj[key] = value

                objects.append(obj)

    except Exception as e:
        print(f"Error parsing TSV: {e}")

    return objects


def calculate_percentiles(values, percentiles=[5, 25, 50, 75, 95]):
    """Calculate percentiles for a list of values."""
    if not values:
        return {}

    sorted_vals = sorted(values)
    n = len(sorted_vals)

    result = {}
    for p in percentiles:
        idx = int(n * p / 100)
        idx = min(idx, n - 1)
        result[f'p{p}'] = sorted_vals[idx]

    return result


def create_histogram(values, bins=10, width=40):
    """Create ASCII histogram."""
    if not values:
        return "No data"

    min_val = min(values)
    max_val = max(values)

    if min_val == max_val:
        return f"All values = {min_val}"

    bin_width = (max_val - min_val) / bins
    counts = [0] * bins

    for v in values:
        bin_idx = min(int((v - min_val) / bin_width), bins - 1)
        counts[bin_idx] += 1

    max_count = max(counts)
    lines = []

    for i, count in enumerate(counts):
        bin_start = min_val + i * bin_width
        bin_end = bin_start + bin_width
        bar_len = int((count / max_count) * width) if max_count > 0 else 0
        bar = '█' * bar_len
        lines.append(f"  {bin_start:7.1f}-{bin_end:7.1f} | {bar} ({count})")

    return '\n'.join(lines)


def analyze_acquisition(acq_dir):
    """Perform comprehensive analysis of an acquisition."""
    print(f"\n{Colors.BOLD}{'═' * 70}{Colors.ENDC}")
    print(f"{Colors.BOLD}  ACQUISITION ANALYSIS REPORT{Colors.ENDC}")
    print(f"{Colors.BOLD}{'═' * 70}{Colors.ENDC}\n")

    print(f"{Colors.CYAN}Directory:{Colors.ENDC} {acq_dir}")

    # Find TSV file
    tsv_path = find_tsv_file(acq_dir)
    if not tsv_path:
        print(f"{Colors.RED}No TSV file found in {acq_dir}{Colors.ENDC}")
        return

    print(f"{Colors.CYAN}TSV File:{Colors.ENDC} {os.path.basename(tsv_path)}")

    # Parse objects
    objects = parse_tsv(tsv_path)
    if not objects:
        print(f"{Colors.RED}No objects found in TSV{Colors.ENDC}")
        return

    print(f"\n{Colors.GREEN}Total Objects: {len(objects)}{Colors.ENDC}")

    # Count unique images
    images = set(obj.get('img_file_name', '') for obj in objects)
    print(f"Unique Images: {len(images)}")
    print(f"Avg Objects/Image: {len(objects) / len(images):.2f}" if images else "")

    # Extract numeric measurements
    equivalent_diameters = [obj.get('object_equivalent_diameter', 0) for obj in objects if obj.get('object_equivalent_diameter')]
    areas = [obj.get('object_area', 0) for obj in objects if obj.get('object_area')]
    elongations = [obj.get('object_elongation', 0) for obj in objects if obj.get('object_elongation')]
    circularities = [obj.get('object_circ.', 0) for obj in objects if obj.get('object_circ.')]
    solidities = [obj.get('object_solidity', 0) for obj in objects if obj.get('object_solidity')]
    blur_scores = [obj.get('object_blur_score', 0) for obj in objects if obj.get('object_blur_score')]

    # Size Distribution
    print(f"\n{Colors.CYAN}{'─' * 60}{Colors.ENDC}")
    print(f"{Colors.CYAN}SIZE DISTRIBUTION (Equivalent Diameter, µm){Colors.ENDC}")
    print(f"{Colors.CYAN}{'─' * 60}{Colors.ENDC}")

    if equivalent_diameters:
        stats = calculate_percentiles(equivalent_diameters)
        print(f"  Min: {min(equivalent_diameters):.1f}  Max: {max(equivalent_diameters):.1f}  Mean: {sum(equivalent_diameters)/len(equivalent_diameters):.1f}")
        print(f"  P5: {stats.get('p5', 0):.1f}  P25: {stats.get('p25', 0):.1f}  P50: {stats.get('p50', 0):.1f}  P75: {stats.get('p75', 0):.1f}  P95: {stats.get('p95', 0):.1f}")
        print(f"\n{create_histogram(equivalent_diameters)}")

    # Area Distribution
    print(f"\n{Colors.CYAN}{'─' * 60}{Colors.ENDC}")
    print(f"{Colors.CYAN}AREA DISTRIBUTION (pixels²){Colors.ENDC}")
    print(f"{Colors.CYAN}{'─' * 60}{Colors.ENDC}")

    if areas:
        stats = calculate_percentiles(areas)
        print(f"  Min: {min(areas):.0f}  Max: {max(areas):.0f}  Mean: {sum(areas)/len(areas):.0f}")
        print(f"  P50: {stats.get('p50', 0):.0f}  P95: {stats.get('p95', 0):.0f}")

    # Morphology Analysis
    print(f"\n{Colors.CYAN}{'─' * 60}{Colors.ENDC}")
    print(f"{Colors.CYAN}MORPHOLOGY METRICS{Colors.ENDC}")
    print(f"{Colors.CYAN}{'─' * 60}{Colors.ENDC}")

    if elongations:
        print(f"\n  Elongation (major/minor axis):")
        print(f"    Mean: {sum(elongations)/len(elongations):.2f}  Min: {min(elongations):.2f}  Max: {max(elongations):.2f}")
        # Classify shapes
        round_count = sum(1 for e in elongations if e < 1.5)
        oval_count = sum(1 for e in elongations if 1.5 <= e < 3)
        elongated_count = sum(1 for e in elongations if e >= 3)
        print(f"    Round (<1.5): {round_count} ({100*round_count/len(elongations):.1f}%)")
        print(f"    Oval (1.5-3): {oval_count} ({100*oval_count/len(elongations):.1f}%)")
        print(f"    Elongated (>3): {elongated_count} ({100*elongated_count/len(elongations):.1f}%)")

    if circularities:
        print(f"\n  Circularity (4π·area/perimeter²):")
        print(f"    Mean: {sum(circularities)/len(circularities):.3f}  (1.0 = perfect circle)")
        high_circ = sum(1 for c in circularities if c > 0.8)
        print(f"    High circularity (>0.8): {high_circ} ({100*high_circ/len(circularities):.1f}%)")

    if solidities:
        print(f"\n  Solidity (area/convex_hull_area):")
        print(f"    Mean: {sum(solidities)/len(solidities):.3f}  (1.0 = convex shape)")
        solid_count = sum(1 for s in solidities if s > 0.9)
        irregular_count = sum(1 for s in solidities if s < 0.7)
        print(f"    Solid (>0.9): {solid_count} ({100*solid_count/len(solidities):.1f}%)")
        print(f"    Irregular (<0.7): {irregular_count} ({100*irregular_count/len(solidities):.1f}%)")

    # Blur Analysis
    print(f"\n{Colors.CYAN}{'─' * 60}{Colors.ENDC}")
    print(f"{Colors.CYAN}FOCUS QUALITY (Blur Scores){Colors.ENDC}")
    print(f"{Colors.CYAN}{'─' * 60}{Colors.ENDC}")

    if blur_scores and any(b > 0 for b in blur_scores):
        valid_blur = [b for b in blur_scores if b > 0]
        print(f"  Mean Blur Score: {sum(valid_blur)/len(valid_blur):.2f}")
        sharp_count = sum(1 for b in valid_blur if b > 50)
        blurry_count = sum(1 for b in valid_blur if b < 20)
        print(f"  Sharp (>50): {sharp_count} ({100*sharp_count/len(valid_blur):.1f}%)")
        print(f"  Blurry (<20): {blurry_count} ({100*blurry_count/len(valid_blur):.1f}%)")
    else:
        print(f"  {Colors.DIM}Blur metrics not available{Colors.ENDC}")

    # Time Analysis
    print(f"\n{Colors.CYAN}{'─' * 60}{Colors.ENDC}")
    print(f"{Colors.CYAN}TEMPORAL DISTRIBUTION{Colors.ENDC}")
    print(f"{Colors.CYAN}{'─' * 60}{Colors.ENDC}")

    times = [obj.get('object_time', '') for obj in objects if obj.get('object_time')]
    if times:
        # Group by minute
        by_minute = defaultdict(int)
        for t in times:
            minute = t[:5] if len(t) >= 5 else t  # HH:MM
            by_minute[minute] += 1

        sorted_minutes = sorted(by_minute.items())
        if sorted_minutes:
            print(f"  Start: {sorted_minutes[0][0]}  End: {sorted_minutes[-1][0]}")
            print(f"  Objects by minute:")
            for minute, count in sorted_minutes[-10:]:  # Last 10 minutes
                bar = '█' * min(count // 2, 40)
                print(f"    {minute}: {bar} ({count})")

    # Summary Statistics
    print(f"\n{Colors.CYAN}{'─' * 60}{Colors.ENDC}")
    print(f"{Colors.CYAN}SUMMARY{Colors.ENDC}")
    print(f"{Colors.CYAN}{'─' * 60}{Colors.ENDC}")

    print(f"""
  Total Objects Detected:  {len(objects)}
  Total Images Processed:  {len(images)}
  Objects per Image:       {len(objects)/max(len(images),1):.2f}

  Median Object Size:      {calculate_percentiles(equivalent_diameters).get('p50', 0):.1f} µm
  95th Percentile Size:    {calculate_percentiles(equivalent_diameters).get('p95', 0):.1f} µm

  Sample ID:               {objects[0].get('sample_id', 'N/A') if objects else 'N/A'}
  Acquisition ID:          {objects[0].get('acq_id', 'N/A') if objects else 'N/A'}
  Pixel Size:              {objects[0].get('process_pixel', 'N/A') if objects else 'N/A'} µm
""")


def export_csv_summary(objects, output_path):
    """Export a simplified CSV summary for external analysis."""
    if not objects:
        return

    fields = [
        'object_id', 'object_equivalent_diameter', 'object_area',
        'object_elongation', 'object_circ.', 'object_solidity',
        'object_blur_score', 'img_file_name', 'object_time'
    ]

    with open(output_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for obj in objects:
            writer.writerow({k: obj.get(k, '') for k in fields})

    print(f"Exported summary to: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description='Analyze PlanktoScope live segmentation acquisitions',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('acq_dir', nargs='?',
                        help='Acquisition directory to analyze')
    parser.add_argument('--latest', action='store_true',
                        help='Analyze most recent acquisition')
    parser.add_argument('--export-csv', type=str, metavar='PATH',
                        help='Export simplified CSV for external analysis')

    args = parser.parse_args()

    if args.latest or not args.acq_dir:
        acq_dir = find_latest_acquisition()
        if not acq_dir:
            print(f"{Colors.RED}No acquisitions found{Colors.ENDC}")
            sys.exit(1)
    else:
        acq_dir = args.acq_dir

    if not os.path.isdir(acq_dir):
        print(f"{Colors.RED}Directory not found: {acq_dir}{Colors.ENDC}")
        sys.exit(1)

    analyze_acquisition(acq_dir)

    if args.export_csv:
        tsv_path = find_tsv_file(acq_dir)
        if tsv_path:
            objects = parse_tsv(tsv_path)
            export_csv_summary(objects, args.export_csv)


if __name__ == '__main__':
    main()
