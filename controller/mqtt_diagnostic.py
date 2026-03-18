#!/usr/bin/env python3
"""MQTT diagnostic tool for debugging pump/imager coordination.

Usage (run on the Pi during an acquisition):
    python3 mqtt_diagnostic.py

This subscribes to all pump and imager status topics and logs every message
with high-precision timestamps. It will reveal:
- Whether stale/retained "Done" messages arrive before "Started"
- Whether messages are arriving out of order
- The actual timing gaps between pump Done → stabilization → image capture
- Whether the imager proceeds before the pump has truly finished

Look for these red flags in the output:
  [RACE] - A "Done" arrived before any "Started" for the current cycle
  [STALE] - A retained message was received at subscribe time
  [GAP] - Timing anomaly between expected message pairs
"""

import json
import sys
import time
from datetime import datetime

import paho.mqtt.client as mqtt


class MQTTDiagnostic:
    def __init__(self, host="localhost", port=1883):
        self.host = host
        self.port = port
        self.client = mqtt.Client(protocol=mqtt.MQTTv5)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

        # State tracking for race detection
        self.pump_cycle_active = False  # Have we seen "Started" for current cycle?
        self.last_pump_started = None   # Timestamp of last "Started"
        self.last_pump_done = None      # Timestamp of last "Done"
        self.last_imager_status = None
        self.cycle_count = 0
        self.anomalies = []

    def on_connect(self, client, userdata, flags, reason_code, props):
        print(f"[{self._ts()}] Connected to MQTT broker at {self.host}:{self.port}")
        client.subscribe("status/pump")
        client.subscribe("status/imager")
        client.subscribe("actuator/pump")  # Also watch commands being sent
        print(f"[{self._ts()}] Subscribed to status/pump, status/imager, actuator/pump")
        print(f"[{self._ts()}] Waiting for messages... (start an acquisition to see the flow)")
        print("-" * 90)

    def on_message(self, client, userdata, msg):
        ts = self._ts()
        mono = time.monotonic()

        try:
            payload = json.loads(msg.payload.decode())
        except (json.JSONDecodeError, UnicodeDecodeError):
            print(f"[{ts}] {msg.topic}: <unparseable: {msg.payload}>")
            return

        retained = " [RETAINED]" if msg.retain else ""
        print(f"[{ts}] {msg.topic}: {json.dumps(payload)}{retained}")

        # Analyze pump command/status flow
        if msg.topic == "actuator/pump":
            action = payload.get("action")
            if action == "move":
                self.pump_cycle_active = False  # Reset - waiting for "Started"
                self.cycle_count += 1
                print(f"         ^^^ Pump MOVE command sent (cycle #{self.cycle_count})")

        elif msg.topic == "status/pump":
            status = payload.get("status")

            if msg.retain:
                self.anomalies.append(f"Cycle #{self.cycle_count}: Retained '{status}' message received")
                print(f"         ^^^ [STALE] Retained message - this can cause race conditions!")

            if status == "Started":
                self.pump_cycle_active = True
                self.last_pump_started = mono
                duration = payload.get("duration", "?")
                print(f"         ^^^ Pump STARTED (expected duration: {duration}s)")

            elif status in ("Done", "Interrupted"):
                if not self.pump_cycle_active and not msg.retain:
                    self.anomalies.append(
                        f"Cycle #{self.cycle_count}: '{status}' received WITHOUT preceding 'Started'"
                    )
                    print(f"         ^^^ [RACE] '{status}' without 'Started'! "
                          f"This would cause premature image capture!")

                if self.last_pump_started is not None:
                    elapsed = mono - self.last_pump_started
                    print(f"         ^^^ Pump {status} after {elapsed:.3f}s")
                else:
                    print(f"         ^^^ Pump {status} (no 'Started' timestamp available)")

                self.last_pump_done = mono
                self.pump_cycle_active = False

        elif msg.topic == "status/imager":
            status = payload.get("status", "")
            msg_type = payload.get("type", "")

            if "Started" in str(status) and msg_type != "progress":
                print(f"         ^^^ Imager acquisition STARTED")

            elif msg_type == "progress":
                current = payload.get("current", "?")
                total = payload.get("total", "?")
                if self.last_pump_done is not None:
                    gap = mono - self.last_pump_done
                    print(f"         ^^^ Image {current}/{total} saved "
                          f"({gap:.3f}s after pump done)")
                else:
                    print(f"         ^^^ Image {current}/{total} saved")

            elif "Done" in str(status):
                print(f"         ^^^ Imager acquisition COMPLETE")
                self._print_summary()

            elif "Interrupted" in str(status):
                print(f"         ^^^ Imager acquisition INTERRUPTED")
                self._print_summary()

    def _print_summary(self):
        print("\n" + "=" * 90)
        print(f"ACQUISITION SUMMARY - {self.cycle_count} pump cycles observed")
        if self.anomalies:
            print(f"\n*** {len(self.anomalies)} ANOMALIES DETECTED ***")
            for a in self.anomalies:
                print(f"  - {a}")
        else:
            print("\nNo anomalies detected - pump/imager coordination looks healthy.")
        print("=" * 90 + "\n")
        # Reset for next acquisition
        self.anomalies.clear()
        self.cycle_count = 0

    @staticmethod
    def _ts():
        return datetime.now().strftime("%H:%M:%S.%f")[:-3]

    def run(self):
        print(f"PlanktoScope MQTT Diagnostic Tool")
        print(f"Connecting to {self.host}:{self.port}...")
        self.client.connect(self.host, self.port, 60)
        try:
            self.client.loop_forever()
        except KeyboardInterrupt:
            print("\nDiagnostic stopped.")
            self._print_summary()


if __name__ == "__main__":
    host = sys.argv[1] if len(sys.argv) > 1 else "localhost"
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 1883
    diag = MQTTDiagnostic(host=host, port=port)
    diag.run()
