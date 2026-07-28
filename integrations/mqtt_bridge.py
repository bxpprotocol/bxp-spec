#!/usr/bin/env python3
"""
BXP MQTT Bridge
Subscribes to an MQTT topic, converts payloads to BXP format,
and submits them to a BXP node.

Install:
    pip install paho-mqtt

Usage:
    python mqtt_bridge.py \
        --broker mqtt.example.com \
        --topic "sensors/air/#" \
        --server http://localhost:5000 \
        --token bxp_your_token

Payload format expected on MQTT topic:
    {
        "lat": 5.6037,
        "lon": -0.1870,
        "pm25": 47.2,
        "no2": 18.3,
        "temp": 29.0,
        "humidity": 78.0
    }

Or use --payload-format to specify a different mapping.
"""

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "sdk" / "python"))
from bxp_sdk import BXPClient, AGENT_UNITS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] bxp.mqtt — %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
log = logging.getLogger("bxp.mqtt")

try:
    import paho.mqtt.client as mqtt
    HAS_MQTT = True
except ImportError:
    HAS_MQTT = False


# ─── Payload mapping ──────────────────────────────────────────

# Maps MQTT payload field names → BXP keyword args for BXPClient.submit()
DEFAULT_FIELD_MAP = {
    "lat":      "latitude",
    "latitude": "latitude",
    "lon":      "longitude",
    "lng":      "longitude",
    "longitude":"longitude",
    "pm25":     "pm25",
    "pm2_5":    "pm25",
    "pm10":     "pm10",
    "no2":      "no2",
    "o3":       "o3",
    "co":       "co",
    "so2":      "so2",
    "tvoc":     "tvoc",
    "temp":     "temp",
    "temperature": "temp",
    "humidity": "humidity",
    "rh":       "humidity",
}


def convert_payload(payload_str: str, field_map: dict) -> dict:
    """Convert an MQTT payload string to BXP submit kwargs."""
    try:
        raw = json.loads(payload_str)
    except json.JSONDecodeError:
        raise ValueError(f"Invalid JSON payload: {payload_str[:100]}")

    kwargs = {}
    for src_key, bxp_key in field_map.items():
        if src_key in raw and raw[src_key] is not None:
            kwargs[bxp_key] = float(raw[src_key])

    if "latitude" not in kwargs or "longitude" not in kwargs:
        raise ValueError("Payload missing lat/lon fields")

    return kwargs


# ─── MQTT client ──────────────────────────────────────────────

class BXPMQTTBridge:
    def __init__(
        self,
        broker:     str,
        topic:      str,
        server_url: str,
        token:      str = None,
        port:       int = 1883,
        qos:        int = 0,
        field_map:  dict = None,
        offline_queue: bool = True,
    ):
        if not HAS_MQTT:
            raise ImportError("paho-mqtt is required: pip install paho-mqtt")

        self.topic     = topic
        self.field_map = field_map or DEFAULT_FIELD_MAP
        self.client_bxp = BXPClient(server_url, device_token=token)
        self.stats = {"received": 0, "submitted": 0, "failed": 0, "skipped": 0}

        if offline_queue:
            from bxp_sdk import OfflineQueue
            self.queue = OfflineQueue("~/.bxp/mqtt_queue.json")
        else:
            self.queue = None

        self.mqtt = mqtt.Client()
        self.mqtt.on_connect    = self._on_connect
        self.mqtt.on_message    = self._on_message
        self.mqtt.on_disconnect = self._on_disconnect

        log.info("Connecting to MQTT broker %s:%d", broker, port)
        self.mqtt.connect(broker, port, keepalive=60)

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            log.info("Connected to MQTT broker — subscribing to '%s'", self.topic)
            client.subscribe(self.topic)
        else:
            log.error("MQTT connect failed, rc=%d", rc)

    def _on_disconnect(self, client, userdata, rc):
        log.warning("MQTT disconnected rc=%d — will auto-reconnect", rc)

    def _on_message(self, client, userdata, msg):
        self.stats["received"] += 1
        payload = msg.payload.decode("utf-8", errors="replace")
        log.debug("MQTT msg topic=%s payload=%s", msg.topic, payload[:120])

        try:
            kwargs = convert_payload(payload, self.field_map)
        except ValueError as e:
            log.warning("Payload parse error: %s", e)
            self.stats["skipped"] += 1
            return

        try:
            result = self.client_bxp.submit(**kwargs)
            if result.get("success"):
                log.info(
                    "Submitted reading id=%s hri=%.1f level=%s",
                    result["readingId"], result["bxpHri"], result["level"]
                )
                self.stats["submitted"] += 1
                # If there was a queue, flush it now server is back
                if self.queue and self.queue.size() > 0:
                    flush = self.queue.flush(self.client_bxp)
                    log.info("Queue flush: %s", flush)
            else:
                raise RuntimeError(result.get("error", "Unknown error"))

        except Exception as e:
            log.warning("Submit failed: %s — queuing", e)
            self.stats["failed"] += 1
            if self.queue:
                self.queue.push(**kwargs)

    def run(self):
        log.info("BXP MQTT Bridge running. Press Ctrl+C to stop.")
        try:
            self.mqtt.loop_forever()
        except KeyboardInterrupt:
            log.info("Stopping. Stats: %s", self.stats)
            self.mqtt.disconnect()


# ─── CLI ─────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(
        description="BXP MQTT Bridge — subscribe to sensor topics and submit to a BXP node"
    )
    p.add_argument("--broker", required=True, help="MQTT broker hostname")
    p.add_argument("--topic",  required=True, help="MQTT topic pattern (e.g. sensors/#)")
    p.add_argument("--server", default=os.environ.get("BXP_SERVER_URL", "http://localhost:5000"),
                   help="BXP node URL")
    p.add_argument("--token",  default=os.environ.get("BXP_DEVICE_TOKEN", ""),
                   help="BXP device token")
    p.add_argument("--port",   type=int, default=1883)
    p.add_argument("--no-queue", action="store_true",
                   help="Disable offline queue (drop readings when server is down)")
    args = p.parse_args()

    if not HAS_MQTT:
        print("Error: paho-mqtt not installed. Run: pip install paho-mqtt")
        sys.exit(1)

    bridge = BXPMQTTBridge(
        broker=args.broker,
        topic=args.topic,
        server_url=args.server,
        token=args.token or None,
        port=args.port,
        offline_queue=not args.no_queue,
    )
    bridge.run()


if __name__ == "__main__":
    main()
