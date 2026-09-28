#!/usr/bin/env python3
"""
BXP OpenAQ Importer
====================
Converts OpenAQ v3 API data into valid BXP records (.bxp / .bxp.json),
and optionally submits them to a BXP node.

WHY THIS EXISTS
---------------
BXP is far more useful on day one bridging data that already exists than
waiting for native-device adoption. OpenAQ aggregates thousands of
government reference monitors and low-cost sensor networks worldwide
(https://openaq.org) — it is exactly the kind of source BXP should be
able to faithfully carry, tier, and re-exchange, especially as some
government-run monitoring feeds are being discontinued for funding
reasons rather than because the air got cleaner.

This importer intentionally does the conservative thing on trust: it
only marks a converted reading `VALIDATED` when OpenAQ's own metadata
says the source is a reference-grade monitor (`isMonitor: true`); every
other source is carried through as `UNVALIDATED`, per SPEC.md §5.5.1 —
importing a feed does not launder its accuracy.

USAGE
-----
    # Live (requires network + an OpenAQ API key: https://explore.openaq.org):
    python3 openaq_import.py --lat 5.5571 --lon -0.1969 --radius 10000 \\
        --api-key $OPENAQ_API_KEY --out-dir ./imported

    # Submit straight to a BXP node instead of writing files:
    python3 openaq_import.py --lat 5.5571 --lon -0.1969 --radius 10000 \\
        --api-key $OPENAQ_API_KEY --server http://localhost:5000 --token bxp_xxx

    # Offline / test mode, no network or API key required — replays a
    # saved OpenAQ API response fixture through the exact same conversion
    # path used for live data (see fixtures/openaq_sample_locations.json
    # and tests/test_openaq_import.py):
    python3 openaq_import.py --fixture fixtures/openaq_sample_locations.json \\
        --out-dir ./imported

NOTE ON TESTING
---------------
This sandbox has no outbound network access, so the live HTTP path
(fetch_locations / fetch_latest) could not be exercised against the
real api.openaq.org in this environment. The request construction is
written directly from OpenAQ's published v3 OpenAPI operation
references (locations_get_v3_locations_get, latest resource docs) --
but a developer with network access should confirm against the live
API before depending on this in production. What IS verified here,
end-to-end, is the conversion logic: OpenAQ JSON -> BXP record ->
validate_bxp_record(), against a realistic fixture
(tests/test_openaq_import.py).
"""

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "sdk" / "python"))
from bxp_sdk import _build_bxp_record, BXPClient  # noqa: E402

OPENAQ_BASE_URL = "https://api.openaq.org/v3"

# OpenAQ parameter "name" -> BXP agentId (SPEC.md §6). OpenAQ's own units
# accompany each measurement and are passed through as-is (unit is a
# free-text field on a BXP agent entry; SPEC.md does not mandate SI here).
OPENAQ_PARAM_TO_BXP_AGENT = {
    "pm25": "PM2_5",
    "pm1": "PM1",
    "pm10": "PM10",
    "bc": "BC",
    "co": "CO",
    "co2": "CO2",
    "no2": "NO2",
    "so2": "SO2",
    "o3": "O3",
    "h2s": "H2S",
    "nh3": "NH3",
    "relativehumidity": "RH",
    "temperature": "TEMP",
    "pressure": "PRESS",
    "um003": None,  # particle-count channels OpenAQ sometimes reports; no BXP agent yet
}


class OpenAQImportError(Exception):
    pass


def _openaq_device_uuid(location_id) -> str:
    """
    Deterministic UUID for an OpenAQ location, so BXP's `deviceUuid` field
    (which SPEC.md §5 defines as a UUID, not an arbitrary string) stays
    stable across repeated imports of the same OpenAQ location -- that
    stability is what lets a `.bxp` consumer treat "OpenAQ location 8118"
    as one consistent provenance source over time, per SPEC.md §7 Stage 6.
    """
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"https://api.openaq.org/v3/locations/{location_id}"))


def _http_get_json(url: str, api_key: Optional[str]) -> dict:
    req = urllib.request.Request(url)
    if api_key:
        req.add_header("X-API-Key", api_key)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise OpenAQImportError(f"OpenAQ API error {e.code} for {url}: {e.read()[:500]}")
    except urllib.error.URLError as e:
        raise OpenAQImportError(f"Could not reach OpenAQ API at {url}: {e}")


def fetch_locations(lat: float, lon: float, radius_m: int, api_key: Optional[str],
                     limit: int = 100) -> list:
    """
    GET /v3/locations?coordinates={lat},{lon}&radius={radius_m}
    Per OpenAQ's v3 OpenAPI reference, `coordinates` is "latitude,longitude"
    (e.g. "38.9074,-77.0373"); `radius` is meters, max 25000.
    """
    if radius_m > 25000:
        raise ValueError("OpenAQ's /v3/locations radius is capped at 25000 meters")
    params = {
        "coordinates": f"{lat},{lon}",
        "radius": radius_m,
        "limit": limit,
    }
    url = f"{OPENAQ_BASE_URL}/locations?{urllib.parse.urlencode(params)}"
    data = _http_get_json(url, api_key)
    return data.get("results", [])


def fetch_latest(location_id: int, api_key: Optional[str]) -> list:
    """GET /v3/locations/{id}/latest -> latest value per sensor at that location."""
    url = f"{OPENAQ_BASE_URL}/locations/{location_id}/latest"
    data = _http_get_json(url, api_key)
    return data.get("results", [])


def openaq_location_to_bxp_records(location: dict, latest_results: list) -> list:
    """
    Convert one OpenAQ location + its latest sensor readings into one or
    more BXP reading records (one per timestamp present in latest_results,
    since BXP groups agents measured at the same instant into one record;
    OpenAQ's /latest can return slightly different timestamps per sensor).

    This is the function exercised directly by tests/test_openaq_import.py
    against a fixture, independent of any network access.
    """
    sensors_by_id = {s["id"]: s for s in location.get("sensors", [])}
    is_monitor = bool(location.get("isMonitor"))
    coords = location.get("coordinates") or {}
    lat = coords.get("latitude")
    lon = coords.get("longitude")
    provider_name = (location.get("provider") or {}).get("name", "unknown")
    location_name = location.get("name") or f"openaq-location-{location.get('id')}"

    # Group latest readings by timestamp so co-measured agents land in one record.
    by_timestamp: dict = {}
    for reading in latest_results:
        ts_iso = (reading.get("datetime") or {}).get("utc") if isinstance(reading.get("datetime"), dict) else reading.get("datetime")
        sensor = sensors_by_id.get(reading.get("sensorsId"))
        if sensor is None:
            continue
        param_name = (sensor.get("parameter") or {}).get("name", "").lower()
        agent_id = OPENAQ_PARAM_TO_BXP_AGENT.get(param_name)
        if not agent_id:
            continue  # not yet mapped to a BXP agent (e.g. raw particle counts)
        unit = (sensor.get("parameter") or {}).get("units", "")
        by_timestamp.setdefault(ts_iso, []).append({
            "agentId": agent_id,
            "value": reading.get("value"),
            "unit": unit,
            "method": "reference" if is_monitor else "low_cost_sensor",
        })

    records = []
    for ts_iso, agents in by_timestamp.items():
        if not ts_iso or not agents:
            continue
        import datetime as _dt
        try:
            dt = _dt.datetime.fromisoformat(ts_iso.replace("Z", "+00:00"))
        except ValueError:
            continue
        ts_us = int(dt.timestamp() * 1_000_000)

        quality = (
            {"flag": "VALIDATED", "confidence": 0.95,
             "qcMethod": f"openaq-reference-monitor:{provider_name}", "notes": None}
            if is_monitor else
            {"flag": "UNVALIDATED", "confidence": 0.5,
             "qcMethod": "bxp-sdk-auto", "notes": [f"Imported via OpenAQ from {provider_name}; no correction applied"]}
        )

        record = _build_bxp_record({
            "latitude": lat,
            "longitude": lon,
            "timestampUs": ts_us,
            "agents": agents,
            "context": {"importedFrom": "openaq", "openaqLocationName": location_name,
                        "openaqProvider": provider_name},
        }, device_uuid=_openaq_device_uuid(location.get('id')))
        record["quality"] = quality
        # _build_bxp_record() already computed payloadHash based on its own
        # auto-assessed quality; overwriting quality above invalidates that
        # hash, so it MUST be recomputed here or every imported record would
        # fail its own integrity check (validate_bxp_record would report
        # "Payload hash mismatch" on data that was never actually tampered).
        import hashlib as _hashlib
        check = {k: v for k, v in record.items() if k != "payloadHash"}
        payload_str = json.dumps(check, sort_keys=True, separators=(",", ":"), default=str)
        record["payloadHash"] = "sha256:" + _hashlib.sha256(payload_str.encode()).hexdigest()
        records.append(record)

    return records


def import_from_fixture(fixture_path: str) -> list:
    """
    Offline path used for testing and demos: fixture is a JSON file shaped
    like {"locations": [...], "latest_by_location": {"<id>": [...]}}
    (see fixtures/openaq_sample_locations.json).
    """
    data = json.loads(Path(fixture_path).read_text())
    all_records = []
    for location in data.get("locations", []):
        latest = data.get("latest_by_location", {}).get(str(location["id"]), [])
        all_records.extend(openaq_location_to_bxp_records(location, latest))
    return all_records


def import_live(lat: float, lon: float, radius_m: int, api_key: Optional[str]) -> list:
    locations = fetch_locations(lat, lon, radius_m, api_key)
    all_records = []
    for location in locations:
        latest = fetch_latest(location["id"], api_key)
        all_records.extend(openaq_location_to_bxp_records(location, latest))
    return all_records


def main():
    p = argparse.ArgumentParser(description="Import OpenAQ data into BXP")
    p.add_argument("--lat", type=float, help="Latitude of search center")
    p.add_argument("--lon", type=float, help="Longitude of search center")
    p.add_argument("--radius", type=int, default=10000, help="Search radius in meters (max 25000)")
    p.add_argument("--api-key", default=None, help="OpenAQ API key (https://explore.openaq.org)")
    p.add_argument("--fixture", default=None, help="Path to an offline OpenAQ fixture JSON (no network needed)")
    p.add_argument("--out-dir", default=None, help="Directory to write .bxp.json files to")
    p.add_argument("--binary", action="store_true", help="Write .bxp binary instead of .bxp.json")
    p.add_argument("--server", default=None, help="BXP node URL to POST records to instead of writing files")
    p.add_argument("--token", default=None, help="Device/API token for --server")
    args = p.parse_args()

    if args.fixture:
        records = import_from_fixture(args.fixture)
    elif args.lat is not None and args.lon is not None:
        records = import_live(args.lat, args.lon, args.radius, args.api_key)
    else:
        p.error("Provide either --fixture, or --lat/--lon for a live import")
        return

    print(f"Converted {len(records)} OpenAQ reading(s) into BXP records")

    if args.server:
        client = BXPClient(base_url=args.server, device_token=args.token)
        for r in records:
            result = client.submit_record(r)
            if not result.get("success"):
                print(f"  WARNING: failed to submit reading for {r['deviceUuid']}: {result.get('error')}")
        print(f"Submitted {len(records)} record(s) to {args.server}")
    elif args.out_dir:
        out_dir = Path(args.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        for i, r in enumerate(records):
            ext = "bxp" if args.binary else "bxp.json"
            path = out_dir / f"openaq_{r['deviceUuid']}_{r['timestampUs']}.{ext}"
            if args.binary:
                from bxp_binary import encode_bxp_binary
                path.write_bytes(encode_bxp_binary(r))
            else:
                path.write_text(json.dumps(r, indent=2, default=str))
        print(f"Wrote {len(records)} file(s) to {out_dir}")
    else:
        print(json.dumps(records, indent=2, default=str))


if __name__ == "__main__":
    main()
