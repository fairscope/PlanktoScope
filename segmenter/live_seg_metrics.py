#!/usr/bin/env python3
"""
live_seg_metrics.py - A Nice Real-time metrics analyzer for PlanktoScope Live Segmentation

Monitors:
- Processing time per image
- Throughput (images/second, objects/second)
- Queue depth (pending images)
- Object detection statistics
- System resource usage
- Error rates

Usage:
    python3 live_seg_metrics.py              # Real-time monitoring mode
    python3 live_seg_metrics.py --summary    # Analyze completed acquisition
    python3 live_seg_metrics.py --watch      # Continuous watch mode with refresh
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Optional

# Configuration
IMG_BASE = "/home/pi/data/img"
OBJECTS_BASE = "/home/pi/data/objects"
LIVE_STATS_FILE = "/tmp/seg_live_stats.json"
METRICS_LOG_FILE = "/tmp/seg_metrics.jsonl"

# ANSI colors for terminal output
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


def clear_screen():
    """Clear terminal screen."""
    os.system('clear' if os.name == 'posix' else 'cls')


def get_system_stats():
    """Get CPU and memory usage."""
    try:
        # CPU usage
        with open('/proc/loadavg', 'r') as f:
            load_avg = f.read().split()[:3]

        # Memory usage
        with open('/proc/meminfo', 'r') as f:
            meminfo = {}
            for line in f:
                parts = line.split(':')
                if len(parts) == 2:
                    key = parts[0].strip()
                    val = int(parts[1].strip().split()[0])
                    meminfo[key] = val

        total_mem = meminfo.get('MemTotal', 1)
        avail_mem = meminfo.get('MemAvailable', 0)
        used_mem = total_mem - avail_mem
        mem_percent = (used_mem / total_mem) * 100

        return {
            'load_1min': float(load_avg[0]),
            'load_5min': float(load_avg[1]),
            'load_15min': float(load_avg[2]),
            'mem_used_mb': used_mem / 1024,
            'mem_total_mb': total_mem / 1024,
            'mem_percent': mem_percent,
        }
    except Exception as e:
        return {'error': str(e)}


def get_active_acquisition():
    """Find the currently active acquisition directory."""
    try:
        # Look for most recently modified image directory
        today = datetime.now().strftime("%Y-%m-%d")
        today_dir = os.path.join(IMG_BASE, today)

        if not os.path.exists(today_dir):
            return None

        latest_time = 0
        latest_acq = None

        for sample_dir in os.listdir(today_dir):
            sample_path = os.path.join(today_dir, sample_dir)
            if not os.path.isdir(sample_path):
                continue

            for acq_dir in os.listdir(sample_path):
                acq_path = os.path.join(sample_path, acq_dir)
                if not os.path.isdir(acq_path):
                    continue

                mtime = os.path.getmtime(acq_path)
                if mtime > latest_time:
                    latest_time = mtime
                    latest_acq = acq_path

        return latest_acq
    except Exception:
        return None


def count_images_in_dir(directory):
    """Count .jpg images in directory."""
    try:
        return len([f for f in os.listdir(directory) if f.endswith('.jpg') and not f.endswith('_debug.jpg')])
    except Exception:
        return 0


def get_queue_depth(acq_dir, objects_dir):
    """Calculate how many images are waiting to be processed."""
    if not acq_dir:
        return 0, 0

    img_count = count_images_in_dir(acq_dir)

    # Count processed images by looking at live stats
    try:
        if os.path.exists(LIVE_STATS_FILE):
            with open(LIVE_STATS_FILE, 'r') as f:
                stats = json.load(f)
            processed = stats.get('total_images', 0)
        else:
            processed = 0
    except Exception:
        processed = 0

    return img_count, max(0, img_count - processed)


def parse_journalctl_logs(service_name, since_minutes=5):
    """Parse recent logs from a systemd service."""
    try:
        cmd = [
            'journalctl', '-u', service_name,
            '--since', f'{since_minutes} minutes ago',
            '--no-pager', '-o', 'short-precise'
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        return result.stdout.split('\n')
    except Exception:
        return []


def analyze_segmentation_output():
    """Analyze segmentation metrics from JSONL log file."""
    metrics = {
        'processing_times': [],
        'objects_per_image': [],
        'errors': 0,
        'successes': 0,
        'methods': {},
        'timestamps': [],
    }

    # Read from metrics log file (primary source)
    if os.path.exists(METRICS_LOG_FILE):
        try:
            with open(METRICS_LOG_FILE, 'r') as f:
                for line in f:
                    try:
                        data = json.loads(line.strip())
                        metrics['successes'] += 1
                        if 'processing_time_ms' in data:
                            metrics['processing_times'].append(data['processing_time_ms'])
                        if 'objects_found' in data:
                            metrics['objects_per_image'].append(data['objects_found'])
                        if 'timestamp' in data:
                            metrics['timestamps'].append(data['timestamp'])
                        method = data.get('method', 'unknown')
                        metrics['methods'][method] = metrics['methods'].get(method, 0) + 1
                    except json.JSONDecodeError:
                        pass
        except Exception:
            pass

    # Fallback: also check journalctl for errors in case something goes wrong
    lines = parse_journalctl_logs('planktoscope-org.controller.imager.service', since_minutes=10)
    for line in lines:
        if '"error"' in line.lower() and 'segment' in line.lower():
            metrics['errors'] += 1

    return metrics


def subscribe_mqtt_realtime():
    """Subscribe to MQTT for real-time segmentation updates."""
    try:
        import paho.mqtt.client as mqtt

        metrics = {
            'last_update': None,
            'total_objects': 0,
            'total_images': 0,
            'output_dir': '',
        }

        def on_message(client, userdata, msg):
            try:
                data = json.loads(msg.payload.decode())
                metrics['last_update'] = time.time()
                metrics['total_objects'] = data.get('total_objects', 0)
                metrics['total_images'] = data.get('total_images', 0)
                metrics['output_dir'] = data.get('output_dir', '')
            except Exception:
                pass

        client = mqtt.Client()
        client.on_message = on_message
        client.connect("localhost", 1883, 60)
        client.subscribe("status/segmentation")
        client.loop_start()

        return client, metrics
    except ImportError:
        return None, None


def format_time_ms(ms):
    """Format milliseconds nicely."""
    if ms < 1000:
        return f"{ms:.0f}ms"
    else:
        return f"{ms/1000:.2f}s"


def calculate_statistics(values):
    """Calculate min, max, avg, p50, p95 for a list of values."""
    if not values:
        return {'min': 0, 'max': 0, 'avg': 0, 'p50': 0, 'p95': 0, 'count': 0}

    sorted_vals = sorted(values)
    n = len(sorted_vals)

    return {
        'min': min(values),
        'max': max(values),
        'avg': sum(values) / n,
        'p50': sorted_vals[int(n * 0.5)],
        'p95': sorted_vals[int(n * 0.95)] if n > 1 else sorted_vals[0],
        'count': n,
    }


def print_metrics_dashboard(metrics, sys_stats, acq_info, mqtt_data=None):
    """Print a formatted metrics dashboard that looks nice."""
    clear_screen()

    print(f"{Colors.BOLD}{Colors.HEADER}╔══════════════════════════════════════════════════════════════════╗{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.HEADER}║         PLANKTOSCOPE LIVE SEGMENTATION METRICS                   ║{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.HEADER}╚══════════════════════════════════════════════════════════════════╝{Colors.ENDC}")
    print()

    # Acquisition Info
    print(f"{Colors.CYAN}▶ ACQUISITION{Colors.ENDC}")
    if acq_info:
        print(f"  Directory: {acq_info}")
        total_imgs, pending = get_queue_depth(acq_info, None)
        print(f"  Total Images: {total_imgs}")

        if pending > 0:
            print(f"  {Colors.YELLOW}Queue Depth: {pending} images pending{Colors.ENDC}")
        else:
            print(f"  {Colors.GREEN}Queue Depth: 0 (caught up){Colors.ENDC}")
    else:
        print(f"  {Colors.DIM}No active acquisition found{Colors.ENDC}")
    print()

    # MQTT Real-time Data on the Machine
    if mqtt_data and mqtt_data.get('last_update'):
        age = time.time() - mqtt_data['last_update']
        freshness = f"{Colors.GREEN}LIVE{Colors.ENDC}" if age < 5 else f"{Colors.YELLOW}{age:.0f}s ago{Colors.ENDC}"
        print(f"{Colors.CYAN}▶ LIVE STATUS{Colors.ENDC} ({freshness})")
        print(f"  Total Images Processed: {mqtt_data.get('total_images', 0)}")
        print(f"  Total Objects Detected: {mqtt_data.get('total_objects', 0)}")
        if mqtt_data.get('total_images', 0) > 0:
            avg_obj = mqtt_data.get('total_objects', 0) / mqtt_data.get('total_images', 1)
            print(f"  Avg Objects/Image: {avg_obj:.1f}")
        print()

    # Processing Time Stats
    print(f"{Colors.CYAN}▶ PROCESSING TIME{Colors.ENDC}")
    time_stats = calculate_statistics(metrics.get('processing_times', []))
    if time_stats['count'] > 0:
        print(f"  Samples: {time_stats['count']}")
        print(f"  Min: {format_time_ms(time_stats['min'])}  |  Max: {format_time_ms(time_stats['max'])}  |  Avg: {format_time_ms(time_stats['avg'])}")
        print(f"  P50: {format_time_ms(time_stats['p50'])}  |  P95: {format_time_ms(time_stats['p95'])}")

        # Throughput estimate based on processing time
        if time_stats['avg'] > 0:
            throughput = 1000 / time_stats['avg']
            print(f"  {Colors.GREEN}Processing Throughput: {throughput:.2f} images/sec{Colors.ENDC}")

        # Actual throughput based on timestamps
        timestamps = metrics.get('timestamps', [])
        if len(timestamps) >= 2:
            elapsed = timestamps[-1] - timestamps[0]
            if elapsed > 0:
                actual_throughput = (len(timestamps) - 1) / elapsed
                print(f"  {Colors.GREEN}Actual Throughput: {actual_throughput:.2f} images/sec{Colors.ENDC}")
    else:
        print(f"  {Colors.DIM}No data available{Colors.ENDC}")
    print()

    # Objects Per Image Stats
    print(f"{Colors.CYAN}▶ OBJECTS PER IMAGE{Colors.ENDC}")
    obj_stats = calculate_statistics(metrics.get('objects_per_image', []))
    if obj_stats['count'] > 0:
        print(f"  Min: {obj_stats['min']:.0f}  |  Max: {obj_stats['max']:.0f}  |  Avg: {obj_stats['avg']:.1f}")
        print(f"  P50: {obj_stats['p50']:.0f}  |  P95: {obj_stats['p95']:.0f}")
    else:
        print(f"  {Colors.DIM}No data available{Colors.ENDC}")
    print()

    # Success/Error Rates
    print(f"{Colors.CYAN}▶ RELIABILITY{Colors.ENDC}")
    successes = metrics.get('successes', 0)
    errors = metrics.get('errors', 0)
    total = successes + errors
    if total > 0:
        success_rate = (successes / total) * 100
        color = Colors.GREEN if success_rate > 95 else (Colors.YELLOW if success_rate > 80 else Colors.RED)
        print(f"  Successes: {successes}  |  Errors: {errors}")
        print(f"  {color}Success Rate: {success_rate:.1f}%{Colors.ENDC}")
    else:
        print(f"  {Colors.DIM}No data available{Colors.ENDC}")
    print()

    # Segmentation Methods Used
    methods = metrics.get('methods', {})
    if methods:
        print(f"{Colors.CYAN}▶ SEGMENTATION METHODS{Colors.ENDC}")
        for method, count in sorted(methods.items(), key=lambda x: -x[1]):
            print(f"  {method}: {count}")
        print()

    # System Resources
    print(f"{Colors.CYAN}▶ SYSTEM RESOURCES{Colors.ENDC}")
    if 'error' not in sys_stats:
        load_color = Colors.GREEN if sys_stats['load_1min'] < 2 else (Colors.YELLOW if sys_stats['load_1min'] < 4 else Colors.RED)
        mem_color = Colors.GREEN if sys_stats['mem_percent'] < 70 else (Colors.YELLOW if sys_stats['mem_percent'] < 90 else Colors.RED)

        print(f"  {load_color}Load: {sys_stats['load_1min']:.2f} / {sys_stats['load_5min']:.2f} / {sys_stats['load_15min']:.2f}{Colors.ENDC}")
        print(f"  {mem_color}Memory: {sys_stats['mem_used_mb']:.0f}MB / {sys_stats['mem_total_mb']:.0f}MB ({sys_stats['mem_percent']:.1f}%){Colors.ENDC}")
    else:
        print(f"  {Colors.DIM}Unable to read system stats{Colors.ENDC}")
    print()

    print(f"{Colors.DIM}Last updated: {datetime.now().strftime('%H:%M:%S')} | Press Ctrl+C to exit{Colors.ENDC}")


def print_summary_report(acq_dir):
    """Print a final summary report for a completed acquisition."""
    print(f"\n{Colors.BOLD}═══════════════════════════════════════════════════════════════════{Colors.ENDC}")
    print(f"{Colors.BOLD}          LIVE SEGMENTATION SUMMARY REPORT{Colors.ENDC}")
    print(f"{Colors.BOLD}═══════════════════════════════════════════════════════════════════{Colors.ENDC}\n")

    if acq_dir:
        print(f"Acquisition: {acq_dir}")

    # Load final stats
    try:
        if os.path.exists(LIVE_STATS_FILE):
            with open(LIVE_STATS_FILE, 'r') as f:
                stats = json.load(f)
            print(f"\nTotal Images Processed: {stats.get('total_images', 0)}")
            print(f"Total Objects Detected: {stats.get('total_objects', 0)}")
            if stats.get('total_images', 0) > 0:
                avg = stats.get('total_objects', 0) / stats.get('total_images', 1)
                print(f"Average Objects/Image: {avg:.2f}")
    except Exception as e:
        print(f"Could not load stats: {e}")

    # Analyze recent logs for timing
    metrics = analyze_segmentation_output()

    print(f"\n{Colors.CYAN}Processing Time Statistics:{Colors.ENDC}")
    time_stats = calculate_statistics(metrics.get('processing_times', []))
    if time_stats['count'] > 0:
        print(f"  Samples analyzed: {time_stats['count']}")
        print(f"  Minimum: {format_time_ms(time_stats['min'])}")
        print(f"  Maximum: {format_time_ms(time_stats['max'])}")
        print(f"  Average: {format_time_ms(time_stats['avg'])}")
        print(f"  Median (P50): {format_time_ms(time_stats['p50'])}")
        print(f"  95th Percentile: {format_time_ms(time_stats['p95'])}")

        if time_stats['avg'] > 0:
            throughput = 1000 / time_stats['avg']
            print(f"\n  Effective Throughput: {throughput:.2f} images/second")
            print(f"  Time for 100 images: {format_time_ms(100 * time_stats['avg'])}")

    print(f"\n{Colors.CYAN}Object Detection Statistics:{Colors.ENDC}")
    obj_stats = calculate_statistics(metrics.get('objects_per_image', []))
    if obj_stats['count'] > 0:
        print(f"  Min objects/image: {obj_stats['min']:.0f}")
        print(f"  Max objects/image: {obj_stats['max']:.0f}")
        print(f"  Average: {obj_stats['avg']:.2f}")

    print(f"\n{Colors.CYAN}Reliability:{Colors.ENDC}")
    successes = metrics.get('successes', 0)
    errors = metrics.get('errors', 0)
    if successes + errors > 0:
        rate = (successes / (successes + errors)) * 100
        print(f"  Success rate: {rate:.1f}% ({successes} succeeded, {errors} errors)")

    print(f"\n{Colors.CYAN}Methods Used:{Colors.ENDC}")
    for method, count in metrics.get('methods', {}).items():
        print(f"  {method}: {count} images")

    print()


def run_watch_mode():
    """Run continuous monitoring with auto-refresh."""
    print("Starting live segmentation metrics monitor...")
    print("Connecting to MQTT...")

    mqtt_client, mqtt_data = subscribe_mqtt_realtime()

    if mqtt_client is None:
        print(f"{Colors.YELLOW}Warning: MQTT client not available. Install paho-mqtt for real-time updates.{Colors.ENDC}")
        mqtt_data = {}

    try:
        while True:
            acq_dir = get_active_acquisition()
            metrics = analyze_segmentation_output()
            sys_stats = get_system_stats()

            print_metrics_dashboard(metrics, sys_stats, acq_dir, mqtt_data)

            time.sleep(2)  # Refresh every 2 seconds

    except KeyboardInterrupt:
        print("\n\nStopping metrics monitor...")
        if mqtt_client:
            mqtt_client.loop_stop()
            mqtt_client.disconnect()


def main():
    parser = argparse.ArgumentParser(
        description='PlanktoScope Live Segmentation Metrics Analyzer',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s              # Real-time monitoring dashboard
  %(prog)s --summary    # Print summary of recent acquisition
  %(prog)s --watch      # Alias for default mode
        """
    )
    parser.add_argument('--summary', action='store_true',
                        help='Print summary report instead of live monitoring')
    parser.add_argument('--watch', action='store_true',
                        help='Continuous watch mode (default)')
    parser.add_argument('--acq-dir', type=str,
                        help='Specific acquisition directory to analyze')

    args = parser.parse_args()

    if args.summary:
        acq_dir = args.acq_dir or get_active_acquisition()
        print_summary_report(acq_dir)
    else:
        run_watch_mode()


if __name__ == '__main__':
    main()
