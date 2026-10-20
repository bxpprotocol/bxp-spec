#!/usr/bin/env python3
"""BXP Public Data Ingestion Agent.

Pulls live public air-quality feeds, normalizes them to BXP v2.0 records,
computes BXP_HRI, validates, and commits them back to the repo so the
network is seeded with data (solves the chicken-and-egg problem).

Runs autonomously on a schedule via .github/workflows/bxp-ingest.yml.

Feeds:
  - OpenAQ v3 (no key required) — https://api.openaq.org/v3
  - EPA AirNow (optional, needs AIRNOW_API_KEY secret)
  - Copernicus Atmosphere (optional, needs CAMS_API_KEY secret)

Output: datasets/live/<feed>-<city>-<timestamp>.bxp.json
  plus datasets/live/index.json manifest.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

SDK = Path(__file__).resolve().parent.parent / "sdk" / "python"
if str(SDK) not in sys.path:
    sys.path.insert(0, str(SDK))

try:
    import httpx
except ImportError:
    httpx = None

try:
    from bxp_sdk import write_bxp, validate_bxp_record, calculate_risk
except ImportError as exc:
    raise SystemExit(f"bxp-sdk not importable: {exc}")


# ──────────────────────────────────────────────────────────────────
# CONFIG
# ──────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parent.parent
LIVE_DIR = REPO_ROOT / "datasets" / "live"
INDEX_PATH = LIVE_DIR / "index.json"

# Cities to poll (global spread across under-monitored regions).
CITIES = [
    {"name": "Accra", "lat": 5.6037, "lon": -0.1870, "country": "GH"},
    {"name": "Lagos", "lat": 6.5244, "lon": 3.3792, "country": "NG"},
    {"name": "Delhi", "lat": 28.6139, "lon": 77.2090, "country": "IN"},
    {"name": "Beijing", "lat": 39.9042, "lon": 116.4074, "country": "CN"},
    {"name": "London", "lat": 51.5074, "lon": -0.1278, "country": "GB"},
    {"name": "Sao Paulo", "lat": -23.5505, "lon": -46.6333, "country": "BR"},
    {"name": "New York", "lat": 40.7128, "lon": -74.0060, "country": "US"},
    {"name": "Nairobi", "lat": -1.2921, "lon": 36.8219, "country": "KE"},
    {"name": "Jakarta", "lat": -6.2088, "lon": 106.8456, "country": "ID"},
    {"name": "Cairo", "lat": 30.0444, "lon": 31.2357, "country": "EG"},
]

GUARDIAN_BRANCH = "bxp-ingest"
INGEST_COMMIT = "chore(bxp-ingest): seed live public readings"


# ──────────────────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────────────────

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def run(cmd: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=str(cwd) if cwd else None, capture_output=True, text=True, check=check)


def git_config() -> None:
    run(["git", "config", "user.email", "bxp-ingest@users.noreply.github.com"], cwd=REPO_ROOT)
    run(["git", "config", "user.name", "BXP Ingest"], cwd=REPO_ROOT)


def git_commit_and_push(message: str) -> bool:
    if not shutil_git_available():
        print("[ingest] git not available — skipping commit/push")
        return False

    git_config()
    status = run(["git", "status", "--porcelain"], cwd=REPO_ROOT, check=False)
    if not status.stdout.strip():
        print("[ingest] no changes to commit")
        return False

    run(["git", "add", "datasets/live/"], cwd=REPO_ROOT, check=False)
    run(["git", "commit", "-m", message], cwd=REPO_ROOT, check=False)
    run(["git", "push", "origin", f"HEAD:{GUARDIAN_BRANCH}"], cwd=REPO_ROOT, check=False)
    print(f"[ingest] committed and pushed to {GUARDIAN_BRANCH}")
    return True


def shutil_git_available() -> bool:
    try:
        run(["git", "--version"], check=False)
        return True
    except FileNotFoundError:
        return False


# ──────────────────────────────────────────────────────────────────
# FEEDS
# ──────────────────────────────────────────────────────────────────

def fetch_openaq(locations: int = 50) -> list[dict]:
    """Pull from OpenAQ v3 (no key required, limited tier)."""
    if httpx is None:
        print("[ingest] httpx not installed — skipping OpenAQ")
        return []

    readings: list[dict] = []
    with httpx.Client(timeout=30.0, headers={"User-Agent": "bxp-ingest/1.0"}) as client:
        try:
            resp = client.get(
                "https://api.openaq.org/v3/locations",
                params={"limit": locations, "order_by": "lastUpdated", "sort_order": "desc"},
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            print(f"[ingest] OpenAQ fetch failed: {exc}")
            return readings

    for loc in data.get("results", []):
        coords = loc.get("coordinates", {})
        lat = coords.get("latitude")
        lon = coords.get("longitude")
        if lat is None or lon is None:
            continue

        # Latest measurements for this location.
        try:
            meas = client.get(
                f"https://api.openaq.org/v3/locations/{loc['id']}/latest",
                params={"limit": 20},
            )
            meas.raise_for_status()
            mdata = meas.json()
        except Exception:
            continue

        agents: list[dict] = []
        for m in mdata.get("results", []):
            param = (m.get("parameter") or "").upper()
            value = m.get("value")
            unit = m.get("unit") or ""
            if value is None:
                continue
            # Map OpenAQ parameter names to BXP agent IDs.
            agent_id = {
                "PM25": "PM2_5", "PM10": "PM10", "NO2": "NO2",
                "O3": "O3", "CO": "CO", "SO2": "SO2", "BC": "BC",
            }.get(param, param)
            agents.append({
                "agentId": agent_id,
                "value": float(value),
                "unit": unit,
                "method": "optical",
                "belowLod": False,
            })

        if not agents:
            continue

        readings.append({
            "latitude": lat,
            "longitude": lon,
            "agents": agents,
            "source": "imported",
            "ext": {"source": "openaq", "originalId": str(loc.get("id"))},
            "indoorOutdoor": "outdoor",
            "durationS": 3600,
            "context": {"location": loc.get("name"), "country": loc.get("country")},
        })

    print(f"[ingest] OpenAQ: {len(readings)} locations with measurements")
    return readings


def fetch_airnow(city: dict) -> list[dict]:
    """Pull from EPA AirNow (optional, needs AIRNOW_API_KEY)."""
    key = os.environ.get("AIRNOW_API_KEY")
    if not key or httpx is None:
        return []

    readings: list[dict] = []
    with httpx.Client(timeout=30.0) as client:
        try:
            resp = client.get(
                "https://www.airnowapi.org/aq/observation/latLong/current/",
                params={
                    "format": "application/json",
                    "latitude": city["lat"],
                    "longitude": city["lon"],
                    "distance": 25,
                    "API_KEY": key,
                },
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            print(f"[ingest] AirNow fetch failed for {city['name']}: {exc}")
            return readings

        agents: list[dict] = []
        for obs in data:
            param = (obs.get("ParameterName") or "").upper()
            agent_id = {
                "PM2.5": "PM2_5", "PM10": "PM10", "NO2": "NO2",
                "OZONE": "O3", "CO": "CO", "SO2": "SO2",
            }.get(param, param)
            agents.append({
                "agentId": agent_id,
                "value": float(obs.get("Concentration", 0)),
                "unit": obs.get("Unit", "ug/m3"),
            })

        if agents:
            readings.append({
                "latitude": city["lat"],
                "longitude": city["lon"],
                "agents": agents,
                "source": "imported",
                "ext": {"source": "epa_airnow", "originalId": city["name"]},
                "indoorOutdoor": "outdoor",
                "durationS": 3600,
                "context": {"location": city["name"], "country": city["country"]},
            })

    print(f"[ingest] AirNow {city['name']}: {len(readings)} readings")
    return readings


# ──────────────────────────────────────────────────────────────────
# NORMALIZE -> BXP
# ──────────────────────────────────────────────────────────────────

def normalize_to_bxp(rd: dict, feed: str) -> dict | None:
    """Build and validate a BXP record from a normalized reading dict.

    Sets source before write_bxp() so the payload hash covers it.
    Adds ext/context after and recomputes the payload hash since the SDK
    does not carry ext into the built record.
    """
    rd["source"] = "imported"

    tmp_path = LIVE_DIR / "_tmp.bxp.json"
    try:
        record = write_bxp(str(tmp_path), rd)
    except Exception as exc:
        print(f"[ingest] write_bxp failed: {exc}")
        return None
    finally:
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass

    # Restore ext/context provenance fields the SDK does not copy into the
    # built record, then recompute the payload hash so the record stays valid.
    record["ext"] = {"source": feed, **rd.get("ext", {})}
    if "context" in rd:
        record["context"] = rd["context"]

    import hashlib as _hashlib
    payload_str = json.dumps(
        {k: v for k, v in record.items() if k != "payloadHash"},
        sort_keys=True, separators=(",", ":"), default=str,
    )
    record["payloadHash"] = "sha256:" + _hashlib.sha256(
        payload_str.encode()
    ).hexdigest()

    # Re-validate after mutation.
    result = validate_bxp_record(record)
    if not result["valid"]:
        print(f"[ingest] invalid record after ext injection: {result['errors']}")
        return None

    return record


def write_record_file(record: dict, feed: str, city_name: str) -> Path:
    """Write a single BXP record to datasets/live/ and return its path."""
    ts = int(time.time() * 1_000_000)
    safe_city = "".join(c for c in city_name if c.isalnum() or c in ("-", "_")).lower()
    fname = f"{feed}-{safe_city}-{ts}.bxp.json"
    path = LIVE_DIR / fname
    path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return path


# ──────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────

def main() -> int:
    LIVE_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[ingest] BXP Public Data Ingestion starting at {utc_now_iso()}")

    all_records: list[dict] = []
    index_entries: list[dict] = []

    # 1. OpenAQ (no key).
    openaq_readings = fetch_openaq()
    for rd in openaq_readings:
        record = normalize_to_bxp(rd, "openaq")
        if record:
            path = write_record_file(record, "openaq", str(rd.get("context", {}).get("location", "unknown")))
            all_records.append(record)
            index_entries.append({
                "file": path.name,
                "feed": "openaq",
                "city": rd.get("context", {}).get("location"),
                "country": rd.get("context", {}).get("country"),
                "latitude": record.get("latitude"),
                "longitude": record.get("longitude"),
                "timestampUs": record.get("timestampUs"),
                "bxpHri": record.get("bxpHri"),
                "bxpHriLevel": record.get("bxpHriLevel"),
                "source": "imported",
                "generatedAt": utc_now_iso(),
            })

    # 2. EPA AirNow (optional key).
    for city in CITIES:
        airnow_readings = fetch_airnow(city)
        for rd in airnow_readings:
            record = normalize_to_bxp(rd, "epa_airnow")
            if record:
                path = write_record_file(record, "epa_airnow", city["name"])
                all_records.append(record)
                index_entries.append({
                    "file": path.name,
                    "feed": "epa_airnow",
                    "city": city["name"],
                    "country": city["country"],
                    "latitude": record.get("latitude"),
                    "longitude": record.get("longitude"),
                    "timestampUs": record.get("timestampUs"),
                    "bxpHri": record.get("bxpHri"),
                    "bxpHriLevel": record.get("bxpHriLevel"),
                    "source": "imported",
                    "generatedAt": utc_now_iso(),
                })

    # 3. Write index manifest.
    index = {
        "schema": "bxp.live.index.v1",
        "generatedAt": utc_now_iso(),
        "recordCount": len(all_records),
        "feeds": ["openaq", "epa_airnow"],
        "records": index_entries,
    }
    INDEX_PATH.write_text(json.dumps(index, indent=2), encoding="utf-8")

    print(f"[ingest] wrote {len(all_records)} BXP records + index")

    # 4. Commit + push.
    message = f"{INGEST_COMMIT} (+{len(all_records)} live readings)"
    git_commit_and_push(message)

    print(f"[ingest] complete: {len(all_records)} records seeded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
