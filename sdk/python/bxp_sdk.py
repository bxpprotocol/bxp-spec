"""
BXP Python SDK v2.1
Breathe Exposure Protocol

Install:
    pip install bxp-sdk          # once published
    pip install bxp-sdk[async]   # with async HTTP client
    or: copy this file into your project

Usage:
    from bxp_sdk import BXPClient, AsyncBXPClient, write_bxp, read_bxp, calculate_risk

    # Calculate risk from raw values
    risk = calculate_risk(pm25=67.0, no2=31.0, duration="24h", population="sensitive")
    print(risk)  # {'score': 72.4, 'level': 'HIGH', ...}

    # Write a .bxp file
    write_bxp("my_reading.bxp.json", {
        "latitude": 5.6037,
        "longitude": -0.1870,
        "agents": [{"agentId": "PM2_5", "value": 47.2, "unit": "ug/m3"}]
    })

    # Read a .bxp file
    data = read_bxp("my_reading.bxp.json")

    # Submit to a BXP server (sync)
    client = BXPClient("http://localhost:5000", device_token="your_token")
    client.submit(latitude=5.6037, longitude=-0.1870, pm25=47.2, no2=18.3)

    # Submit to a BXP server (async)
    async with AsyncBXPClient("http://localhost:5000") as client:
        await client.submit(latitude=5.6037, longitude=-0.1870, pm25=47.2)
"""

import json
import sys
import uuid
import time
import hashlib
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Union

# Ensure bxp_binary.py (sibling module, same dir) is importable regardless
# of the caller's cwd or sys.path — needed by write_bxp_binary/read_bxp_binary.
sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    import urllib.request
    import urllib.error
    HAS_URLLIB = True
except ImportError:
    HAS_URLLIB = False

try:
    import httpx as _httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False


# ─────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────

BXP_VERSION = "2.0"
SUPPORTED_MAJOR_VERSION = int(BXP_VERSION.split(".")[0])

WHO_THRESHOLDS = {
    "PM2_5": 15.0, "PM10": 45.0, "NO2": 25.0,
    "O3": 100.0,   "CO": 4.0,    "SO2": 40.0,
    "TVOC": 500.0, "BENZ": 1.0,  "FORM": 8.0,
    "PB": 0.5,     "HG": 1.0,    "H2S": 7.0,
}

HRI_WEIGHTS = {
    "PM2_5": 0.35, "PM10": 0.15, "NO2": 0.15,
    "O3": 0.12,    "CO": 0.10,   "SO2": 0.05,
    "TVOC": 0.04,  "BENZ": 0.02, "FORM": 0.02,
}

# Upper bound of each band. Bands are contiguous (no gaps): a score falls
# into the first band whose upper bound is >= score. Do not leave gaps
# between bands (e.g. 20/21, 40/41) — any score landing in a gap silently
# fell through to the CLEAN default, which is exactly the kind of bug this
# must not reintroduce.
RISK_LEVELS = [
    (20,  "CLEAN",     "#00C851",
     "No health risk.",
     "Enjoy outdoor activities freely."),
    (40,  "MODERATE",  "#FFBB33",
     "Acceptable for most.",
     "Sensitive groups: limit prolonged heavy exertion outdoors."),
    (60,  "ELEVATED",  "#FF8800",
     "Reduce heavy outdoor exertion.",
     "Sensitive groups: avoid outdoor exertion."),
    (75,  "HIGH",      "#CC0000",
     "Wear N95 outdoors. Close windows.",
     "Sensitive groups: stay indoors. Use air purifier."),
    (90,  "VERY_HIGH", "#9B0000",
     "Avoid all outdoor activity. N95 mandatory if outside.",
     "Everyone: stay indoors. Seek medical help if symptomatic."),
    (100, "HAZARDOUS", "#4A0000",
     "Emergency. Stay indoors. Evacuate if possible.",
     "Everyone: evacuate to cleaner air. Seek medical attention."),
]

BASE32 = "0123456789bcdefghjkmnpqrstuvwxyz"

AGENT_UNITS = {
    "PM1": "ug/m3", "PM2_5": "ug/m3", "PM10": "ug/m3",
    "BC": "ug/m3",  "CO": "ppm",      "CO2": "ppm",
    "NO2": "ppb",   "SO2": "ppb",     "O3": "ppb",
    "H2S": "ppb",   "NH3": "ppm",     "TVOC": "ppb",
    "BENZ": "ppb",  "FORM": "ppb",    "TOLU": "ppm",
    "TEMP": "C",    "RH": "%",        "PRESS": "hPa",
    "UV": "index",  "PB": "ug/m3",    "HG": "ug/m3",
}


# ─────────────────────────────────────────────────────────────
# GEOHASH
# ─────────────────────────────────────────────────────────────

def encode_geohash(lat: float, lon: float, precision: int = 7) -> str:
    """Encode lat/lon to geohash string."""
    lat_r = [-90.0, 90.0]
    lon_r = [-180.0, 180.0]
    bits  = [16, 8, 4, 2, 1]
    bi    = 0
    even  = True
    result, ch = "", 0

    while len(result) < precision:
        if even:
            mid = (lon_r[0] + lon_r[1]) / 2
            if lon >= mid: ch |= bits[bi]; lon_r[0] = mid
            else:          lon_r[1] = mid
        else:
            mid = (lat_r[0] + lat_r[1]) / 2
            if lat >= mid: ch |= bits[bi]; lat_r[0] = mid
            else:          lat_r[1] = mid
        even = not even
        if bi < 4: bi += 1
        else:      result += BASE32[ch]; bi = 0; ch = 0

    return result


# ─────────────────────────────────────────────────────────────
# CORE FUNCTIONS
# ─────────────────────────────────────────────────────────────

def calculate_risk(
    pm25:       Optional[float] = None,
    pm10:       Optional[float] = None,
    no2:        Optional[float] = None,
    o3:         Optional[float] = None,
    co:         Optional[float] = None,
    so2:        Optional[float] = None,
    tvoc:       Optional[float] = None,
    agents:     Optional[list]  = None,
    duration:   str = "1h",
    population: str = "general"
) -> dict:
    """
    Calculate BXP Health Risk Index.

    Args:
        pm25, pm10, no2, o3, co, so2, tvoc: Individual agent values
        agents: List of {"agentId": str, "value": float} dicts
        duration: "1h" | "8h" | "24h"
        population: "general" | "sensitive"

    Returns:
        dict with score, level, color, advice, breakdown

    Example:
        risk = calculate_risk(pm25=67.0, no2=31.0, duration="8h")
        print(risk["score"])   # 72.4
        print(risk["level"])   # HIGH
    """
    agent_list = list(agents or [])

    named = {
        "PM2_5": pm25, "PM10": pm10, "NO2": no2,
        "O3": o3,      "CO": co,     "SO2": so2, "TVOC": tvoc
    }
    for aid, val in named.items():
        if val is not None:
            agent_list.append({"agentId": aid, "value": float(val)})

    raw = 0.0
    breakdown = {}
    d_factor = {"1h": 1.0, "8h": 1.2, "24h": 1.5}.get(duration, 1.0)
    v_factor = {"general": 1.0, "sensitive": 1.3}.get(population, 1.0)

    for a in agent_list:
        aid = a.get("agentId", "")
        val = a.get("value")
        if val is None or aid not in WHO_THRESHOLDS:
            continue
        thr    = WHO_THRESHOLDS[aid]
        w      = HRI_WEIGHTS.get(aid, 0)
        risk   = min(1.0, float(val) / thr)
        contrib = risk * w
        raw    += contrib
        breakdown[aid] = {
            "value":          val,
            "threshold":      thr,
            "normalizedRisk": round(risk, 4),
            "contribution":   round(contrib, 4),
            "exceedsWho":     float(val) > thr
        }

    score = round(min(100.0, raw * 100 * d_factor * v_factor), 2)
    level, color, advice, sadv = RISK_LEVELS[-1][1:]
    for hi, ln, lc, la, lsa in RISK_LEVELS:
        if score <= hi:
            level, color, advice, sadv = ln, lc, la, lsa
            break

    return {
        "score":           score,
        "level":           level,
        "color":           color,
        "advice":          advice,
        "sensitiveAdvice": sadv,
        "duration":        duration,
        "population":      population,
        "breakdown":       breakdown
    }


def _assess_quality(
    agents: list,
    timestamp_us: int,
    lat: Optional[float],
    lon: Optional[float]
) -> tuple:
    notes = []
    now_us = int(time.time() * 1_000_000)

    if not agents:
        return "INVALID", 0.0, ["No agents present"]

    if timestamp_us > now_us + 3_600_000_000:
        notes.append("Timestamp is in the future")
        return "SUSPECT", 0.3, notes

    any_exceeds_who = False
    critical_spike  = False
    for a in agents:
        aid = a.get("agentId", "")
        val = a.get("value")
        if val is None:
            continue
        val = float(val)
        if val < 0:
            notes.append(f"{aid}: negative value {val}")
            return "INVALID", 0.0, notes
        thr = WHO_THRESHOLDS.get(aid)
        if thr is None:
            continue
        if val > thr:
            any_exceeds_who = True
        if val > thr * 5:
            critical_spike = True
            notes.append(f"{aid} value {val} exceeds 5× WHO threshold ({thr})")

    if critical_spike:
        return "SUSPECT", 0.4, notes

    confidence = 0.75 if any_exceeds_who else 0.9
    flag = "UNVALIDATED"
    return flag, confidence, notes


def _build_bxp_record(data: dict, device_uuid: Optional[str] = None) -> dict:
    """
    Shared record-construction logic used by both write_bxp() (JSON) and
    write_bxp_binary() (binary container), so the two representations stay
    semantically identical per spec §5.1 ("Any BXP implementation MUST
    support both and MUST be capable of lossless conversion between them").

    Returns the complete record dict, including payloadHash, but does not
    write anything to disk.
    """
    dev_uuid = device_uuid or str(uuid.uuid4())
    now_us   = int(time.time() * 1_000_000)

    lat = data.get("latitude")
    lon = data.get("longitude")

    # Validate coordinate ranges
    if lat is not None and not -90 <= lat <= 90:
        raise ValueError(f"latitude {lat} out of range (-90 to 90)")
    if lon is not None and not -180 <= lon <= 180:
        raise ValueError(f"longitude {lon} out of range (-180 to 180)")

    geohash = data.get("geohash")
    if not geohash and lat is not None and lon is not None:
        geohash = encode_geohash(lat, lon, 7)

    # Geohash precision check
    if geohash and len(geohash) < 5:
        raise ValueError(f"Geohash precision too low: {len(geohash)} (minimum 5)")

    agents = [dict(a) for a in (data.get("agents") or [])]
    for a in agents:
        aid = a.get("agentId", "?")
        if "value" not in a or a.get("value") is None:
            raise ValueError(f"Agent {aid}: missing required 'value'")
        val = float(a["value"])
        if val < 0:
            raise ValueError(f"{aid}: value must be non-negative, got {val}")
    shorthand = {
        "pm25": "PM2_5", "pm10": "PM10", "no2": "NO2",
        "o3": "O3",      "co": "CO",     "so2": "SO2",
        "tvoc": "TVOC",  "benz": "BENZ", "form": "FORM",
        "temp": "TEMP",  "humidity": "RH", "pressure": "PRESS",
        "uv": "UV",      "co2": "CO2",   "pm1": "PM1",
    }
    for key, aid in shorthand.items():
        if key in data and data[key] is not None:
            val = float(data[key])
            if val < 0:
                raise ValueError(f"{aid}: value must be non-negative, got {val}")
            agents.append({
                "agentId": aid,
                "value":   val,
                "unit":    AGENT_UNITS.get(aid, "canonical")
            })

    if not agents:
        raise ValueError("At least one agent or measurement value is required")

    hri = calculate_risk(
        agents=agents,
        duration={60: "1h", 28800: "8h", 86400: "24h"}.get(
            data.get("durationS", 60), "1h"
        ),
    )

    quality_flag, quality_confidence, qc_notes = _assess_quality(
        agents, data.get("timestampUs", now_us), lat, lon
    )

    record = {
        "bxpVersion":    BXP_VERSION,
        "deviceUuid":    dev_uuid,
        "geohash":       geohash,
        "latitude":      lat,
        "longitude":     lon,
        "timestampUs":   data.get("timestampUs", now_us),
        "durationS":     data.get("durationS", 60),
        "indoorOutdoor": data.get("indoorOutdoor", "outdoor"),
        "source":        data.get("source", "native"),
        "agents":        agents,
        "context":       data.get("context"),
        "quality": {
            "flag":       quality_flag,
            "confidence": quality_confidence,
            "qcMethod":   "bxp-sdk-auto",
            "notes":      qc_notes if qc_notes else None,
        },
        "bxpHri":      hri["score"],
        "bxpHriLevel": hri["level"],
        "bxpHriColor": hri["color"],
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    }

    payload_str = json.dumps(
        {k: v for k, v in record.items() if k != "payloadHash"},
        sort_keys=True, separators=(',', ':'), default=str
    )
    record["payloadHash"] = "sha256:" + hashlib.sha256(
        payload_str.encode()
    ).hexdigest()

    return record


def write_bxp(
    path: Union[str, Path],
    data: dict,
    device_uuid: Optional[str] = None
) -> dict:
    """
    Write a .bxp.json file.

    Args:
        path: File path to write (e.g. "reading.bxp.json")
        data: Dict with reading data. Supported keys:
              latitude, longitude, geohash, timestampUs,
              agents (list), pm25, pm10, no2, o3, co, so2,
              temp, humidity, pressure, tvoc,
              durationS, indoorOutdoor, context
        device_uuid: Optional device UUID (auto-generated if not given)

    Returns:
        The complete BXP record dict
    """
    record = _build_bxp_record(data, device_uuid)
    Path(path).write_text(
        json.dumps(record, indent=2, default=str),
        encoding="utf-8"
    )
    return record


def write_bxp_binary(
    path: Union[str, Path],
    data: dict,
    device_uuid: Optional[str] = None,
    file_type: str = "reading",
    compress: bool = False,
) -> dict:
    """
    Write a binary `.bxp` container file (spec §5.1/5.2) — the compact,
    device-oriented counterpart to write_bxp()'s `.bxp.json`. Builds the
    exact same record (same validation, same HRI calculation, same
    payloadHash) as write_bxp(), then encodes it with the 32-byte binary
    header instead of writing plain JSON.

    Args:
        path: File path to write (e.g. "reading.bxp")
        data: Same fields as write_bxp()
        device_uuid: Optional device UUID (auto-generated if not given)
        file_type: One of "reading", "aggregate", "agent", "device",
                   "alert", "meta" (default "reading")
        compress: If True, gzip-compress the payload (sets header flag bit0)

    Returns:
        The complete BXP record dict (same shape as write_bxp() returns)
    """
    from bxp_binary import encode_bxp_binary
    record = _build_bxp_record(data, device_uuid)
    raw = encode_bxp_binary(record, file_type=file_type, compress=compress)
    Path(path).write_bytes(raw)
    return record


def read_bxp_binary(path: Union[str, Path]) -> dict:
    """
    Read and parse a binary `.bxp` container file. Verifies the header and
    payload CRC32 checksums (raises BXPBinaryError on mismatch) and, like
    read_bxp(), recalculates HRI from the agents present so callers can spot
    a stale or tampered bxpHri field.

    Returns:
        Parsed BXP record dict with the same _integrityOk / _filePath /
        _readAt / _hriRecalculated fields read_bxp() adds, plus a
        "_binaryHeader" dict with the decoded 32-byte header metadata.
    """
    from bxp_binary import decode_bxp_binary
    raw = Path(path).read_bytes()
    decoded = decode_bxp_binary(raw)
    record = decoded["record"]

    record["_integrityOk"] = (
        decoded["headerChecksumOk"] and decoded["payloadChecksumOk"]
    )
    record["_filePath"] = str(path)
    record["_readAt"] = datetime.now(timezone.utc).isoformat()
    record["_binaryHeader"] = decoded["header"]

    agents = record.get("agents", [])
    if agents:
        record["_hriRecalculated"] = calculate_risk(agents=agents)

    return record


def read_bxp(path: Union[str, Path]) -> dict:
    """
    Read and parse a .bxp.json file.

    Returns:
        Parsed BXP record dict with integrity check result
    """
    content = Path(path).read_text(encoding="utf-8")
    record  = json.loads(content)

    claimed_hash = record.get("payloadHash", "")
    check_record = {k: v for k, v in record.items() if k != "payloadHash"}
    payload_str  = json.dumps(
        check_record, sort_keys=True, separators=(',', ':'), default=str
    )
    computed = "sha256:" + hashlib.sha256(payload_str.encode()).hexdigest()

    record["_integrityOk"] = (computed == claimed_hash)
    record["_filePath"]    = str(path)
    record["_readAt"]      = datetime.now(timezone.utc).isoformat()

    agents = record.get("agents", [])
    if agents:
        record["_hriRecalculated"] = calculate_risk(agents=agents)

    return record


def validate_bxp_record(record: dict) -> dict:
    """
    Validate an already-parsed BXP record dict against the BXP v2.0 spec.
    This is the shared core used by both validate_bxp() (.bxp.json on disk)
    and validate_bxp_binary() (binary .bxp on disk) — a record is a record
    regardless of which container it came out of.

    Returns dict with: valid, errors, warnings, summary, record
    """
    errors   = []
    warnings = []

    for field in ["bxpVersion", "deviceUuid", "geohash", "timestampUs", "agents", "source"]:
        if field not in record or record[field] is None:
            errors.append(f"Missing required field: {field}")

    valid_sources = {"native", "imported", "community", "research", "simulated"}
    src = record.get("source")
    if src and src not in valid_sources:
        errors.append(f"Invalid source '{src}' — must be one of: {', '.join(sorted(valid_sources))}")

    gh = record.get("geohash", "")
    if gh and len(gh) < 5:
        errors.append(f"Geohash precision too low: {len(gh)} (minimum 5)")

    lat = record.get("latitude")
    lon = record.get("longitude")
    if lat is not None and not -90 <= lat <= 90:
        errors.append(f"latitude {lat} out of range (-90 to 90)")
    if lon is not None and not -180 <= lon <= 180:
        errors.append(f"longitude {lon} out of range (-180 to 180)")

    agents = record.get("agents", [])
    if not agents:
        errors.append("No agents present")
    else:
        for i, a in enumerate(agents):
            if "agentId" not in a:
                errors.append(f"Agent {i}: missing agentId")
            if "value" not in a:
                errors.append(f"Agent {i}: missing value")
            elif float(a.get("value", 0)) < 0:
                errors.append(f"Agent {i} ({a.get('agentId')}): negative value")

    ts = record.get("timestampUs", 0)
    now_us  = int(time.time() * 1_000_000)
    max_old = now_us - 30 * 86400 * 1_000_000
    if ts > now_us + 3600 * 1_000_000:
        warnings.append("Timestamp is in the future")
    if ts < max_old:
        warnings.append("Timestamp is older than 30 days")

    claimed = record.get("payloadHash", "")
    if claimed:
        check = {k: v for k, v in record.items() if k != "payloadHash"}
        payload_str = json.dumps(check, sort_keys=True,
                                 separators=(',', ':'), default=str)
        computed = "sha256:" + hashlib.sha256(payload_str.encode()).hexdigest()
        if computed != claimed:
            errors.append("Payload hash mismatch — file may be tampered")
    else:
        warnings.append("No payloadHash — integrity unverifiable")

    ver = record.get("bxpVersion", "")
    ver_major = ver.split(".")[0] if ver else ""
    if ver_major and ver_major != str(SUPPORTED_MAJOR_VERSION):
        errors.append(
            f"bxpVersion '{ver}' has major version {ver_major}, but this "
            f"implementation supports major version {SUPPORTED_MAJOR_VERSION} "
            "(SPEC.md §5.8 — a major-version mismatch is not just a warning)"
        )
    # A higher minor version than this SDK currently knows about is fine
    # per SPEC.md §5.8 (unrecognized optional fields are simply ignored) —
    # it is deliberately NOT flagged as a warning here.

    quality = record.get("quality") or {}
    if quality.get("flag") == "VALIDATED":
        any_correction_applied = any(
            (a.get("correction") or {}).get("applied") for a in agents
        )
        explicit_qc = quality.get("qcMethod") and quality["qcMethod"] != "bxp-sdk-auto"
        if not any_correction_applied and not explicit_qc:
            warnings.append(
                "quality.flag is VALIDATED but no agent shows an applied "
                "correction and quality.qcMethod gives no explicit "
                "justification — per SPEC.md §5.5.1, VALIDATED should be "
                "backed by either a correction against a reference "
                "instrument or a stated QC method, not asserted on its own"
            )

    valid = len(errors) == 0
    if valid and not warnings:
        summary = f"VALID BXP v{ver} — {len(agents)} agent(s) — HRI {record.get('bxpHri', 'N/A')}"
    elif valid:
        summary = f"VALID with {len(warnings)} warning(s)"
    else:
        summary = f"INVALID — {len(errors)} error(s)"

    return {"valid": valid, "errors": errors, "warnings": warnings,
            "summary": summary, "record": record}


def validate_bxp(path: Union[str, Path]) -> dict:
    """
    Validate a .bxp.json file against the BXP v2.0 spec.

    Returns dict with: valid, errors, warnings, summary
    """
    try:
        record = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as e:
        return {
            "valid": False, "errors": [f"Cannot parse file: {e}"],
            "warnings": [], "summary": "INVALID — Cannot parse JSON"
        }
    return validate_bxp_record(record)


def validate_bxp_binary(path: Union[str, Path]) -> dict:
    """
    Validate a binary `.bxp` container file: verifies the 32-byte header
    and CRC32 checksums first (spec §5.2), then runs the same field-level
    validation validate_bxp() runs against the decoded record.

    Returns dict with: valid, errors, warnings, summary, record
    """
    from bxp_binary import decode_bxp_binary, BXPBinaryError
    try:
        decoded = decode_bxp_binary(Path(path).read_bytes())
    except BXPBinaryError as e:
        return {
            "valid": False, "errors": [f"Binary container error: {e}"],
            "warnings": [], "summary": "INVALID — Corrupt .bxp binary container"
        }
    result = validate_bxp_record(decoded["record"])
    result["binaryHeader"] = decoded["header"]
    return result


# ─────────────────────────────────────────────────────────────
# OFFLINE QUEUE
# ─────────────────────────────────────────────────────────────

class OfflineQueue:
    """
    Local queue for readings when the server is unreachable.
    Persists readings to a JSON file on disk and flushes when
    the server comes back online.

    Example:
        queue = OfflineQueue("~/.bxp/queue.json")
        queue.push(latitude=5.6037, longitude=-0.1870, pm25=47.2)
        flushed = queue.flush(client)   # push all queued readings
    """

    def __init__(self, path: Union[str, Path] = "~/.bxp/queue.json"):
        self._path = Path(path).expanduser()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _load(self) -> list:
        if not self._path.exists():
            return []
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except Exception:
            return []

    def _save(self, items: list):
        self._path.write_text(
            json.dumps(items, indent=2, default=str),
            encoding="utf-8"
        )

    def push(self, **kwargs) -> int:
        """Queue a reading. Returns the new queue length."""
        with self._lock:
            items = self._load()
            items.append({
                "queuedAt": int(time.time() * 1_000_000),
                **kwargs,
            })
            self._save(items)
            return len(items)

    def size(self) -> int:
        return len(self._load())

    def flush(self, client: "BXPClient") -> dict:
        """
        Submit all queued readings to the server.
        Returns {"flushed": N, "failed": N, "remaining": N}.
        """
        with self._lock:
            items = self._load()
            if not items:
                return {"flushed": 0, "failed": 0, "remaining": 0}

            flushed = failed = 0
            remaining = []
            for item in items:
                try:
                    lat = item.pop("latitude", None)
                    lon = item.pop("longitude", None)
                    item.pop("queuedAt", None)
                    if lat is None or lon is None:
                        failed += 1
                        continue
                    result = client.submit(latitude=lat, longitude=lon, **item)
                    if result.get("success"):
                        flushed += 1
                    else:
                        remaining.append(item)
                        failed += 1
                except Exception:
                    remaining.append(item)
                    failed += 1

            self._save(remaining)
            return {"flushed": flushed, "failed": failed,
                    "remaining": len(remaining)}

    def clear(self):
        with self._lock:
            self._save([])


# ─────────────────────────────────────────────────────────────
# SYNC HTTP CLIENT
# ─────────────────────────────────────────────────────────────

class BXPClient:
    """
    BXP synchronous HTTP client.

    Example:
        client = BXPClient("http://localhost:5000",
                           device_token="bxp_device_abc123")
        result = client.submit(
            latitude=5.6037, longitude=-0.1870,
            pm25=47.2, no2=18.3, temp=29.0
        )
        print(result["bxpHri"])   # 61.2
        print(result["level"])    # HIGH
    """

    def __init__(self, base_url: Optional[str] = None,
                 device_token: Optional[str] = None,
                 device_uuid: Optional[str] = None,
                 timeout: int = 15):
        import os
        self.base_url     = (base_url or os.environ.get(
            "BXP_SERVER_URL", "http://localhost:5000"
        )).rstrip("/")
        self.device_token = device_token
        self.device_uuid  = device_uuid or str(uuid.uuid4())
        self.timeout      = timeout

    def _request(self, method: str, path: str,
                 body: Optional[dict] = None) -> dict:
        url  = f"{self.base_url}{path}"
        data = json.dumps(body).encode() if body else None
        headers = {"Content-Type": "application/json"}
        if self.device_token:
            headers["Authorization"] = f"Bearer {self.device_token}"

        req = urllib.request.Request(
            url, data=data, headers=headers, method=method
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            try:
                return json.loads(e.read().decode())
            except Exception:
                return {"error": f"HTTP {e.code}"}
        except Exception as e:
            return {"error": str(e)}

    def health(self) -> dict:
        """Check server health."""
        return self._request("GET", "/bxp/v2/health")

    def submit(self, latitude: float, longitude: float,
               pm25:      Optional[float] = None,
               pm10:      Optional[float] = None,
               no2:       Optional[float] = None,
               o3:        Optional[float] = None,
               co:        Optional[float] = None,
               so2:       Optional[float] = None,
               temp:      Optional[float] = None,
               humidity:  Optional[float] = None,
               agents:    Optional[list]  = None,
               duration_s: Optional[int] = 60,
               indoor:    bool = False,
               **kwargs) -> dict:
        """Submit a reading to the BXP server."""
        agent_list = list(agents or [])
        shorthand = {
            "PM2_5": pm25, "PM10": pm10, "NO2": no2,
            "O3": o3,      "CO": co,     "SO2": so2,
            "TEMP": temp,  "RH": humidity
        }
        for aid, val in shorthand.items():
            if val is not None:
                agent_list.append({
                    "agentId": aid, "value": val,
                    "unit": AGENT_UNITS.get(aid, "canonical")
                })

        body = {"readings": [{
            "deviceUuid":    self.device_uuid,
            "latitude":      latitude,
            "longitude":     longitude,
            "timestampUs":   int(time.time() * 1_000_000),
            "agents":        agent_list,
            "durationS":     duration_s,
            "indoorOutdoor": "indoor" if indoor else "outdoor",
        }]}

        resp = self._request("POST", "/bxp/v2/readings", body)
        if resp.get("status") == "ok":
            reading = resp["data"]["readings"][0]
            return {
                "readingId":   reading.get("readingId"),
                "geohash":     reading.get("geohash"),
                "bxpHri":      reading.get("bxpHri"),
                "level":       reading.get("bxpHriLevel"),
                "qualityFlag": reading.get("qualityFlag"),
                "success":     True
            }
        return {"success": False, "error": resp.get("errors") or resp.get("error")}

    def submit_record(self, record: dict) -> dict:
        """
        Submit an already-fully-built BXP record as-is (deviceUuid,
        timestampUs, agents, quality, etc. all exactly as given), unlike
        submit() which is a shorthand that always uses this client's own
        device_uuid and the current time.

        This is what an importer/bridge (e.g. integrations/openaq_import.py,
        integrations/mqtt_bridge.py for historical/backfilled data) needs:
        it must preserve the *original* observation's timestamp and
        provenance rather than reporting "now" as when the reading happened.
        """
        body = {"readings": [record]}
        resp = self._request("POST", "/bxp/v2/readings", body)
        if resp.get("status") == "ok":
            reading = resp["data"]["readings"][0]
            return {
                "readingId":   reading.get("readingId"),
                "geohash":     reading.get("geohash"),
                "bxpHri":      reading.get("bxpHri"),
                "level":       reading.get("bxpHriLevel"),
                "qualityFlag": reading.get("qualityFlag"),
                "success":     True
            }
        return {"success": False, "error": resp.get("errors") or resp.get("error")}

    def get_readings(self, geohash: Optional[str] = None,
                     limit: int = 50, offset: int = 0,
                     quality: Optional[str] = None) -> dict:
        """
        Fetch readings from the server with pagination.
        Returns {"readings": [...], "total": N, "offset": N, "limit": N}
        """
        qs = f"?limit={limit}&offset={offset}"
        if geohash: qs += f"&geohash={geohash}"
        if quality: qs += f"&quality={quality}"
        resp = self._request("GET", f"/bxp/v2/readings{qs}")
        return {
            "readings": resp.get("data", {}).get("readings", []),
            "total":    resp.get("total", 0),
            "offset":   resp.get("offset", offset),
            "limit":    resp.get("limit", limit),
        }

    def get_all_readings(self, geohash: Optional[str] = None,
                         page_size: int = 50) -> list:
        """Fetch all readings, automatically paginating."""
        all_results = []
        offset = 0
        while True:
            page = self.get_readings(geohash=geohash, limit=page_size,
                                     offset=offset)
            readings = page.get("readings", [])
            all_results.extend(readings)
            if len(readings) < page_size:
                break
            offset += page_size
            if offset >= page.get("total", 0):
                break
        return all_results

    def get_latest(self, geohash: str) -> Optional[dict]:
        """Get latest reading for a geohash location."""
        resp = self._request("GET", f"/bxp/v2/locations/{geohash}/latest")
        if resp.get("status") == "ok":
            return resp.get("data")
        return None

    def get_city(self, city: str) -> Optional[dict]:
        """Get live BXP data for a city."""
        resp = self._request("GET", f"/bxp/v2/city/{city}")
        if "bxp_hri" in resp:
            return resp
        return None

    def register_device(self, label: Optional[str] = None,
                        owner_hash: Optional[str] = None) -> dict:
        """Register this device and receive a token."""
        resp = self._request("POST", "/bxp/v2/devices/register", {
            "deviceUuid": self.device_uuid,
            "label":      label,
            "ownerHash":  owner_hash,
        })
        if resp.get("status") == "ok":
            data = resp["data"]
            self.device_token = data.get("token")
            return data
        return {"success": False, "error": resp.get("detail")}

    def delete_reading(self, reading_id: str) -> dict:
        """Delete a reading (requires token)."""
        return self._request("DELETE", f"/bxp/v2/readings/{reading_id}")

    def verify_reading(self, reading_id: str) -> dict:
        """Verify integrity of a stored reading."""
        return self._request("GET", f"/bxp/v2/readings/{reading_id}/verify")

    def submit_report(self, latitude: float, longitude: float,
                      report_type: str = "observation",
                      description: Optional[str] = None,
                      severity: Optional[str] = None) -> dict:
        """Submit a community air quality report."""
        return self._request("POST", "/bxp/v2/community/reports", {
            "latitude": latitude, "longitude": longitude,
            "reportType": report_type, "description": description,
            "severity": severity,
        })

    def search(self, q: Optional[str] = None,
               lat: Optional[float] = None,
               lon: Optional[float] = None) -> list:
        """Search readings by city name or coordinates."""
        qs = "?"
        if q:   qs += f"q={q}&"
        if lat: qs += f"lat={lat}&"
        if lon: qs += f"lon={lon}&"
        resp = self._request("GET", f"/bxp/v2/search{qs}")
        return resp.get("data", {}).get("results", [])


# ─────────────────────────────────────────────────────────────
# ASYNC HTTP CLIENT
# ─────────────────────────────────────────────────────────────

class AsyncBXPClient:
    """
    BXP asynchronous HTTP client (requires httpx).

    Example:
        import asyncio
        from bxp_sdk import AsyncBXPClient

        async def main():
            async with AsyncBXPClient("http://localhost:5000") as client:
                result = await client.submit(
                    latitude=5.6037, longitude=-0.1870, pm25=47.2
                )
                print(result)

        asyncio.run(main())
    """

    def __init__(self, base_url: Optional[str] = None,
                 device_token: Optional[str] = None,
                 device_uuid: Optional[str] = None,
                 timeout: int = 15):
        if not HAS_HTTPX:
            raise ImportError(
                "httpx is required for AsyncBXPClient. "
                "Install it with: pip install httpx"
            )
        import os
        self.base_url     = (base_url or os.environ.get(
            "BXP_SERVER_URL", "http://localhost:5000"
        )).rstrip("/")
        self.device_token = device_token
        self.device_uuid  = device_uuid or str(uuid.uuid4())
        self.timeout      = timeout
        self._client: Optional[_httpx.AsyncClient] = None

    async def __aenter__(self):
        headers = {"Content-Type": "application/json"}
        if self.device_token:
            headers["Authorization"] = f"Bearer {self.device_token}"
        self._client = _httpx.AsyncClient(
            base_url=self.base_url,
            headers=headers,
            timeout=self.timeout,
        )
        return self

    async def __aexit__(self, *args):
        if self._client:
            await self._client.aclose()

    async def _request(self, method: str, path: str,
                       body: Optional[dict] = None) -> dict:
        if not self._client:
            raise RuntimeError("Use 'async with AsyncBXPClient() as c:'")
        try:
            resp = await self._client.request(method, path, json=body)
            return resp.json()
        except Exception as e:
            return {"error": str(e)}

    async def health(self) -> dict:
        return await self._request("GET", "/bxp/v2/health")

    async def submit(self, latitude: float, longitude: float,
                     pm25: Optional[float] = None,
                     pm10: Optional[float] = None,
                     no2:  Optional[float] = None,
                     o3:   Optional[float] = None,
                     co:   Optional[float] = None,
                     so2:  Optional[float] = None,
                     agents: Optional[list] = None,
                     duration_s: int = 60,
                     indoor: bool = False) -> dict:
        agent_list = list(agents or [])
        shorthand = {
            "PM2_5": pm25, "PM10": pm10, "NO2": no2,
            "O3": o3, "CO": co, "SO2": so2,
        }
        for aid, val in shorthand.items():
            if val is not None:
                agent_list.append({"agentId": aid, "value": val,
                                   "unit": AGENT_UNITS.get(aid, "canonical")})
        body = {"readings": [{
            "deviceUuid": self.device_uuid,
            "latitude": latitude, "longitude": longitude,
            "timestampUs": int(time.time() * 1_000_000),
            "agents": agent_list,
            "durationS": duration_s,
            "indoorOutdoor": "indoor" if indoor else "outdoor",
        }]}
        resp = await self._request("POST", "/bxp/v2/readings", body)
        if resp.get("status") == "ok":
            reading = resp["data"]["readings"][0]
            return {
                "readingId": reading.get("readingId"),
                "bxpHri":    reading.get("bxpHri"),
                "level":     reading.get("bxpHriLevel"),
                "success":   True,
            }
        return {"success": False, "error": resp.get("detail")}

    async def get_readings(self, geohash: Optional[str] = None,
                           limit: int = 50, offset: int = 0) -> dict:
        qs = f"?limit={limit}&offset={offset}"
        if geohash: qs += f"&geohash={geohash}"
        resp = await self._request("GET", f"/bxp/v2/readings{qs}")
        return {
            "readings": resp.get("data", {}).get("readings", []),
            "total":    resp.get("total", 0),
        }

    async def get_city(self, city: str) -> Optional[dict]:
        resp = await self._request("GET", f"/bxp/v2/city/{city}")
        return resp if "bxp_hri" in resp else None


# ─────────────────────────────────────────────────────────────
# PERSONAL EXPOSURE RECORDS — PROOF-CARRYING LEDGER (SPEC §10.5)
# ─────────────────────────────────────────────────────────────

EXPOSURE_SOURCES = {"open-meteo", "bxp-node", "sensor", "manual"}
EXPOSURE_MEASUREMENT_TYPES = {"measured", "modelled", "manual"}
LOCATION_PRECISIONS = {"none", "city", "area", "exact"}

WHO_PM25_24H = 15.0   # WHO 2021 24-hour guideline, µg/m³
WHO_PM10_24H = 45.0
WHO_NO2_24H  = 25.0


def _canonical_json(obj) -> str:
    """Stable, compact JSON for hash computation — matches TypeScript exactly."""
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), default=str)


def _entry_hash(entry: dict) -> str:
    """SHA-256 of the entry with entryHash removed, compact sorted serialization."""
    check = {k: v for k, v in entry.items() if k != "entryHash"}
    payload = _canonical_json(check)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def createExposureEntry(
    agents: list,
    source: str = "manual",
    measurementType: str = "manual",
    location: Optional[dict] = None,
    previousHash: Optional[str] = None,
    locationPrecision: str = "area",
    qualityNotes: Optional[list] = None,
    timestampUs: Optional[int] = None,
) -> dict:
    """
    Build a single personal exposure record (recordType: "exposure").
    Computes entryHash over the entry excluding itself, per SPEC §10.5.2.

    Args:
        agents: List of {"agentId": str, "value": float, "unit": str}
        source: "open-meteo" | "bxp-node" | "sensor" | "manual"
        measurementType: "measured" | "modelled" | "manual"
        location: {"lat": float, "lon": float, "geohash?": str}
        previousHash: sha256-prefixed hash of prior entry, or None for genesis
        locationPrecision: "none" | "city" | "area" | "exact"
        qualityNotes: optional list of data-quality annotations
        timestampUs: Unix epoch microseconds UTC (now if not given)

    Returns:
        Complete exposure entry dict including entryHash
    """
    if source not in EXPOSURE_SOURCES:
        raise ValueError(f"Invalid source '{source}' — must be one of: {sorted(EXPOSURE_SOURCES)}")
    if measurementType not in EXPOSURE_MEASUREMENT_TYPES:
        raise ValueError(f"Invalid measurementType '{measurementType}' — must be one of: {sorted(EXPOSURE_MEASUREMENT_TYPES)}")
    if locationPrecision not in LOCATION_PRECISIONS:
        raise ValueError(f"Invalid locationPrecision '{locationPrecision}' — must be one of: {sorted(LOCATION_PRECISIONS)}")
    if not agents:
        raise ValueError("At least one agent is required")

    now_us = int(time.time() * 1_000_000)
    entry = {
        "recordType":       "exposure",
        "timestampUs":      timestampUs if timestampUs is not None else now_us,
        "location":         location if location else {"lat": None, "lon": None},
        "agents":           [dict(a) for a in agents],
        "source":           source,
        "measurementType":  measurementType,
        "locationPrecision":locationPrecision,
        "qualityNotes":     qualityNotes if qualityNotes else [],
        "previousHash":     previousHash,
    }
    entry["entryHash"] = _entry_hash(entry)
    return entry


def validateExposureEntry(entry: dict) -> dict:
    """
    Validate a single exposure entry's structure and self-hash.

    Returns dict with: valid, errors, warnings
    """
    errors = []
    warnings = []

    if entry.get("recordType") != "exposure":
        errors.append("recordType must be 'exposure'")
    for field in ["timestampUs", "agents", "source", "measurementType",
                  "locationPrecision", "entryHash"]:
        if field not in entry or entry[field] is None:
            errors.append(f"Missing required field: {field}")

    src = entry.get("source")
    if src and src not in EXPOSURE_SOURCES:
        errors.append(f"Invalid source '{src}'")
    mt = entry.get("measurementType")
    if mt and mt not in EXPOSURE_MEASUREMENT_TYPES:
        errors.append(f"Invalid measurementType '{mt}'")
    lp = entry.get("locationPrecision")
    if lp and lp not in LOCATION_PRECISIONS:
        errors.append(f"Invalid locationPrecision '{lp}'")

    agents = entry.get("agents", [])
    if not agents:
        errors.append("No agents present")
    else:
        for i, a in enumerate(agents):
            if "agentId" not in a:
                errors.append(f"Agent {i}: missing agentId")
            if "value" not in a:
                errors.append(f"Agent {i}: missing value")
            elif float(a.get("value", 0)) < 0:
                errors.append(f"Agent {i} ({a.get('agentId')}): negative value")

    claimed = entry.get("entryHash", "")
    computed = _entry_hash(entry)
    if claimed and claimed != computed:
        errors.append(f"Entry hash mismatch — entry may be tampered (claimed {claimed[:16]}... computed {computed[:16]}...)")

    valid = len(errors) == 0
    summary = f"VALID exposure entry — {len(agents)} agent(s)" if valid else f"INVALID — {len(errors)} error(s)"
    return {"valid": valid, "errors": errors, "warnings": warnings, "summary": summary}


def validateExposureChain(entries: list) -> dict:
    """
    Validate an entire append-only exposure chain.

    Checks each entry's self-hash and that previousHash links match
    the preceding entry's entryHash. Genesis entry must have
    previousHash: null.

    Returns dict with: valid, errors, firstBrokenIndex, entryCount
    """
    errors = []
    first_broken = None

    if not entries:
        return {"valid": False, "errors": ["Chain is empty"],
                "firstBrokenIndex": 0, "entryCount": 0}

    for i, entry in enumerate(entries):
        result = validateExposureEntry(entry)
        if not result["valid"]:
            errors.append(f"Entry {i}: " + "; ".join(result["errors"]))
            if first_broken is None:
                first_broken = i
            continue

        # Chain linkage check
        if i == 0:
            if entry.get("previousHash") is not None:
                errors.append(f"Entry {i}: genesis entry must have previousHash: null")
                if first_broken is None:
                    first_broken = i
        else:
            prev_hash = entries[i - 1].get("entryHash")
            if entry.get("previousHash") != prev_hash:
                errors.append(
                    f"Entry {i}: previousHash does not match entry {i-1} entryHash"
                )
                if first_broken is None:
                    first_broken = i

    valid = len(errors) == 0 and first_broken is None
    return {
        "valid": valid,
        "errors": errors,
        "firstBrokenIndex": first_broken,
        "entryCount": len(entries),
    }


def appendToLedger(
    ledgerPath: str,
    newEntry: dict,
) -> dict:
    """
    Append a new exposure entry to an existing .bxp.json ledger file.
    Reads the current ledger, validates its chain, appends the new entry
    (with previousHash set to the last entry's entryHash), and writes
    back atomically.

    Args:
        ledgerPath: Path to the .bxp.json ledger file
        newEntry: Exposure entry dict (without entryHash; will be computed)

    Returns:
        dict with: valid, entry, ledgerPath, errors
    """
    from pathlib import Path

    path = Path(ledgerPath)
    entries = []

    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            entries = data if isinstance(data, list) else data.get("entries", [])
        except (json.JSONDecodeError, OSError) as e:
            return {"valid": False, "errors": [f"Cannot read ledger: {e}"],
                    "entry": None, "ledgerPath": str(path)}

        # Validate existing chain before appending
        chain = validateExposureChain(entries)
        if not chain["valid"]:
            return {"valid": False, "errors": [f"Existing ledger chain invalid: {chain['errors'][0]}"],
                    "entry": None, "ledgerPath": str(path)}

    previousHash = entries[-1]["entryHash"] if entries else None

    entry = createExposureEntry(
        agents=newEntry.get("agents", []),
        source=newEntry.get("source", "manual"),
        measurementType=newEntry.get("measurementType", "manual"),
        location=newEntry.get("location"),
        previousHash=previousHash,
        locationPrecision=newEntry.get("locationPrecision", "area"),
        qualityNotes=newEntry.get("qualityNotes"),
        timestampUs=newEntry.get("timestampUs"),
    )

    entries.append(entry)

    # Write atomically: write to temp, then replace
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(
        json.dumps(entries, indent=2, default=str),
        encoding="utf-8"
    )
    tmp_path.replace(path)

    return {"valid": True, "entry": entry, "errors": [],
            "ledgerPath": str(path)}


def readLedger(ledgerPath: str) -> dict:
    """
    Read and validate a .bxp.json ledger file.

    Returns dict with: valid, entries, errors, entryCount, chainValid
    """
    from pathlib import Path

    path = Path(ledgerPath)
    if not path.exists():
        return {"valid": False, "errors": [f"Ledger not found: {ledgerPath}"],
                "entries": [], "entryCount": 0, "chainValid": False}

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        return {"valid": False, "errors": [f"Cannot parse ledger: {e}"],
                "entries": [], "entryCount": 0, "chainValid": False}

    entries = data if isinstance(data, list) else data.get("entries", [])
    chain = validateExposureChain(entries)

    return {
        "valid": chain["valid"],
        "entries": entries,
        "errors": chain["errors"],
        "entryCount": len(entries),
        "chainValid": chain["valid"],
    }
