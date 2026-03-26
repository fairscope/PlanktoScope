#!/usr/bin/env python3
"""Benchmark script for PlanktoScope segmenter performance.

Runs segmentation on a test acquisition folder and reports timing, throughput,
memory usage, and object counts. Works on both the original (main) and
parallel (feature/parallel-segmenter) branches.

Usage:
    # On the Pi, from the segmenter/ directory:
    python3 benchmark.py /path/to/acquisition/folder [--workers N] [--runs N] [--validate REF]

    # Examples:
    # Baseline (main branch, or new branch with sequential):
    python3 benchmark.py /data/img/20210122/sample_1/acq_1

    # Parallel mode (new branch only):
    python3 benchmark.py /data/img/20210122/sample_1/acq_1 --workers 3

    # Multiple runs for stable averages:
    python3 benchmark.py /data/img/20210122/sample_1/acq_1 --workers 3 --runs 3

    # Validate output against a reference (baseline) result:
    python3 benchmark.py /data/img/20210122/sample_1/acq_1 --workers 3 --validate baseline_result.json

Workflow:
    1. git checkout main
       python3 benchmark.py /path/to/acq --runs 3
       # Save the output JSON as baseline_result.json

    2. git checkout feature/parallel-segmenter
       python3 benchmark.py /path/to/acq --workers 1 --runs 3
       # Compare sequential-on-new-branch vs baseline

    3. python3 benchmark.py /path/to/acq --workers 3 --runs 3 --validate baseline_result.json
       # Parallel mode, validate objects match baseline
"""

import argparse
import datetime
import json
import os
import platform
import resource
import shutil
import sys
import time


def get_peak_rss_mb():
    """Get peak resident set size in MB (Linux/macOS)."""
    # ru_maxrss is in KB on Linux, bytes on macOS
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if platform.system() == "Darwin":
        return usage / (1024 * 1024)
    return usage / 1024


def prepare_test_folder(source_path, work_dir):
    """Copy acquisition folder to a clean working directory.

    We copy so that:
    - done.txt from previous runs doesn't skip processing
    - Object images from previous runs don't interfere
    - The original data is never modified
    """
    if os.path.exists(work_dir):
        shutil.rmtree(work_dir)

    # Copy only the source images and metadata.json
    os.makedirs(work_dir, exist_ok=True)
    for f in os.listdir(source_path):
        src = os.path.join(source_path, f)
        if os.path.isfile(src) and (
            f.endswith((".jpg", ".JPG", ".jpeg", ".JPEG"))
            or f == "metadata.json"
        ):
            shutil.copy2(src, os.path.join(work_dir, f))

    # Remove done.txt if it was copied
    done_file = os.path.join(work_dir, "done.txt")
    if os.path.exists(done_file):
        os.remove(done_file)

    return work_dir


def count_images(path):
    """Count JPG images in a directory."""
    return len([
        f for f in os.listdir(path)
        if f.lower().endswith((".jpg", ".jpeg"))
    ])


def run_segmentation(data_path, acq_path, worker_count=None):
    """Run the segmenter pipeline and return metrics.

    Args:
        data_path: Root data directory (parent of img/, objects/, export/)
        acq_path: Path to the acquisition folder to segment
        worker_count: Number of workers (None = use branch default)

    Returns:
        dict with timing, object count, and memory metrics
    """
    import multiprocessing

    # Import segmenter (works on both branches)
    from planktoscope.segmenter import SegmenterProcess

    # Create a mock event (never set — we don't use the run loop)
    event = multiprocessing.Event()
    seg = SegmenterProcess(event, data_path)

    # On the new branch, set worker_count if provided
    if worker_count is not None and hasattr(seg, "_SegmenterProcess__worker_count"):
        seg._SegmenterProcess__worker_count = worker_count

    # We need to set up a minimal MQTT mock since _pipe publishes status
    class MockMQTTClient:
        def publish(self, topic, payload):
            pass  # Discard all MQTT publishes during benchmark

    class MockSegmenterClient:
        def __init__(self):
            self.client = MockMQTTClient()

    seg.segmenter_client = MockSegmenterClient()

    # Measure
    rss_before = get_peak_rss_mb()
    start_time = time.monotonic()

    seg.segment_path(acq_path, ecotaxa_export=True)

    elapsed = time.monotonic() - start_time
    rss_after = get_peak_rss_mb()

    # Count results
    objects = seg._SegmenterProcess__global_metadata.get("objects", [])
    object_count = len(objects)

    # Count output files
    obj_path = seg._SegmenterProcess__working_obj_path
    obj_images = len([f for f in os.listdir(obj_path) if f.endswith(".jpg")]) if os.path.exists(obj_path) else 0

    # Check for ecotaxa archive
    archive_path = seg._SegmenterProcess__archive_fn
    archive_exists = os.path.exists(archive_path)
    archive_size_mb = os.path.getsize(archive_path) / (1024 * 1024) if archive_exists else 0

    # Extract object names for validation
    object_names = sorted([obj["name"] for obj in objects])

    return {
        "elapsed_seconds": round(elapsed, 2),
        "object_count": object_count,
        "object_images_saved": obj_images,
        "archive_exists": archive_exists,
        "archive_size_mb": round(archive_size_mb, 2),
        "peak_rss_mb": round(rss_after, 1),
        "rss_delta_mb": round(rss_after - rss_before, 1),
        "object_names": object_names,
    }


def validate_against_reference(result, ref_path):
    """Compare result against a saved reference."""
    with open(ref_path, "r") as f:
        ref = json.load(f)

    issues = []

    # Compare object counts
    if result["object_count"] != ref["object_count"]:
        issues.append(
            f"Object count mismatch: got {result['object_count']}, "
            f"expected {ref['object_count']}"
        )

    # Compare object names (deterministic order check)
    ref_names = ref.get("object_names", [])
    result_names = result.get("object_names", [])
    if ref_names and result_names:
        missing = set(ref_names) - set(result_names)
        extra = set(result_names) - set(ref_names)
        if missing:
            issues.append(f"Missing objects: {sorted(missing)[:10]}{'...' if len(missing) > 10 else ''}")
        if extra:
            issues.append(f"Extra objects: {sorted(extra)[:10]}{'...' if len(extra) > 10 else ''}")

    return issues


def main():
    parser = argparse.ArgumentParser(
        description="Benchmark PlanktoScope segmenter performance"
    )
    parser.add_argument(
        "acquisition_path",
        help="Path to acquisition folder (must contain metadata.json + images)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help="Number of parallel workers (default: branch default). "
        "Only works on feature/parallel-segmenter branch.",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=1,
        help="Number of runs to average (default: 1)",
    )
    parser.add_argument(
        "--validate",
        type=str,
        default=None,
        help="Path to a reference result JSON to validate against",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Save result JSON to this path (for use as --validate reference)",
    )
    args = parser.parse_args()

    acq_path = os.path.abspath(args.acquisition_path)
    if not os.path.exists(os.path.join(acq_path, "metadata.json")):
        print(f"ERROR: No metadata.json found in {acq_path}")
        sys.exit(1)

    image_count = count_images(acq_path)
    if image_count == 0:
        print(f"ERROR: No images found in {acq_path}")
        sys.exit(1)

    # SAFETY: Always use an isolated temp directory as the data root.
    # The segmenter writes to data_path/objects/, data_path/export/, data_path/clean/.
    # We must NEVER point data_path at the real /home/pi/data/ to avoid destroying
    # previously segmented results.
    data_path = os.path.join("/tmp", "benchmark_data")

    # Detect branch
    try:
        import subprocess
        branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            stderr=subprocess.DEVNULL,
        ).decode().strip()
    except Exception:
        branch = "unknown"

    worker_label = args.workers if args.workers else "default"

    print("=" * 60)
    print("PlanktoScope Segmenter Benchmark")
    print("=" * 60)
    print(f"  Branch:           {branch}")
    print(f"  Acquisition:      {acq_path}")
    print(f"  Images:           {image_count}")
    print(f"  Data path:        {data_path}")
    print(f"  Workers:          {worker_label}")
    print(f"  Runs:             {args.runs}")
    print(f"  Date:             {datetime.datetime.now().isoformat()}")
    print("=" * 60)

    all_results = []
    for run_num in range(1, args.runs + 1):
        print(f"\n--- Run {run_num}/{args.runs} ---")

        # Clean the entire temp data root between runs for isolation
        if os.path.exists(data_path):
            shutil.rmtree(data_path)

        # Prepare clean working copy of acquisition images
        # Build the img/ subdirectory structure the segmenter expects
        # e.g., /tmp/benchmark_data/img/DATE/SAMPLE/ACQ/
        img_root = os.path.join(data_path, "img")
        work_dir = os.path.join(img_root, "benchmark_date", "benchmark_sample", "benchmark_acq")
        prepare_test_folder(acq_path, work_dir)

        # Create the output directories the segmenter needs
        for subdir in ["objects", "export", "clean"]:
            os.makedirs(os.path.join(data_path, subdir), exist_ok=True)

        try:
            result = run_segmentation(data_path, work_dir, args.workers)
            all_results.append(result)

            print(f"  Time:             {result['elapsed_seconds']}s")
            print(f"  Objects found:    {result['object_count']}")
            print(f"  Object images:    {result['object_images_saved']}")
            print(f"  Archive created:  {result['archive_exists']}")
            if result["archive_exists"]:
                print(f"  Archive size:     {result['archive_size_mb']} MB")
            print(f"  Peak RSS:         {result['peak_rss_mb']} MB")
            imgs_per_sec = image_count / result["elapsed_seconds"] if result["elapsed_seconds"] > 0 else 0
            objs_per_sec = result["object_count"] / result["elapsed_seconds"] if result["elapsed_seconds"] > 0 else 0
            print(f"  Throughput:       {imgs_per_sec:.2f} images/s, {objs_per_sec:.1f} objects/s")
        except Exception as e:
            print(f"  ERROR: {e}")
            import traceback
            traceback.print_exc()
            all_results.append({"error": str(e)})
        finally:
            pass

    # Summary
    successful = [r for r in all_results if "error" not in r]
    if not successful:
        print("\nAll runs failed!")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    avg_time = sum(r["elapsed_seconds"] for r in successful) / len(successful)
    avg_objects = sum(r["object_count"] for r in successful) / len(successful)
    max_rss = max(r["peak_rss_mb"] for r in successful)
    avg_imgs_per_sec = image_count / avg_time if avg_time > 0 else 0
    avg_objs_per_sec = avg_objects / avg_time if avg_time > 0 else 0

    summary = {
        "branch": branch,
        "workers": args.workers,
        "image_count": image_count,
        "runs": len(successful),
        "avg_elapsed_seconds": round(avg_time, 2),
        "avg_object_count": round(avg_objects),
        "avg_images_per_second": round(avg_imgs_per_sec, 3),
        "avg_objects_per_second": round(avg_objs_per_sec, 1),
        "max_peak_rss_mb": round(max_rss, 1),
        "object_count": successful[-1]["object_count"],
        "object_names": successful[-1].get("object_names", []),
        "date": datetime.datetime.now().isoformat(),
    }

    print(f"  Branch:           {branch}")
    print(f"  Workers:          {worker_label}")
    print(f"  Avg time:         {avg_time:.2f}s ({len(successful)} runs)")
    print(f"  Avg objects:      {int(avg_objects)}")
    print(f"  Throughput:       {avg_imgs_per_sec:.3f} images/s")
    print(f"  Throughput:       {avg_objs_per_sec:.1f} objects/s")
    print(f"  Max peak RSS:     {max_rss:.1f} MB")

    # Validation
    if args.validate:
        print(f"\n--- Validation against {args.validate} ---")
        issues = validate_against_reference(summary, args.validate)
        if issues:
            print("  VALIDATION FAILED:")
            for issue in issues:
                print(f"    - {issue}")
        else:
            print("  VALIDATION PASSED: object counts and names match")

    # Save output
    output_path = args.output
    if output_path is None:
        safe_branch = branch.replace("/", "_")
        worker_str = f"_w{args.workers}" if args.workers else ""
        output_path = f"benchmark_{safe_branch}{worker_str}.json"

    with open(output_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\n  Results saved to: {output_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()
