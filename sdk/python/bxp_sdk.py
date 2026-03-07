"""
BXP Python SDK v2.0
Breathe Exposure Protocol

Install:
    pip install bxp-sdk   (when published)
    or: copy this file into your project

Usage:
    from bxp_sdk import BXPClient, write_bxp, read_bxp, calculate_risk

    # Calculate risk from raw values
    risk = calculate_risk(pm25=67.0, no2=31.0)
    print(risk)  # {'score': 72.4, 'level': 'HIGH', ...}

    # Write a .bxp file
    write_bxp("my_reading.bxp.json", {
        "latitude": 5.6037,
        "longitude": -0.1870,
        "agents": [{"agentId": "PM2_5", "value": 47.2, "unit": "ug/m3"}]
    })

    # Read a .bxp file
    data = read_bxp("my_reading.bxp.json")

    # Submit to a BXP server
    client = BXPClient("http://localhost:8000", device_token="your_token")
    client.submit(latitude=5.6037, longitude=-0.1870, pm25=47.2, no2=18.3)
"""

import json
import uuid
import time
import hashlib
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Union
try:
    import urllib.request
    import urllib.error
    HAS_URLLIB = True
except ImportError:
    HAS_URLLIB = False


# ─────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────

BXP_VERSION = "2.0"

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

RISK_LEVELS = [
    (0,  20,  "CLEAN",     "#00C851",
     "No health risk.",
     "Enjoy outdoor activities freely."),
    (21, 40,  "MODERATE",  "#FFBB33",
     "Acceptable for most.",
     "Sensitive groups: limit prolonged heavy exertion outdoors."),
    (41, 60,  "ELEVATED",  "#FF8800",
     "Reduce heavy outdoor exertion.",
     "Sensitive groups: avoid outdoor exertion."),
    (61, 75,  "HIGH",      "#CC0000",
     "Wear N95 outdoors. Close windows.",
     "Sensitive groups: stay indoors. Use air purifier."),
    (76, 90,  "VERY_HIGH", "#9B0000",
     "Avoid all outdoor activity. N95 mandatory if outside.",
     "Everyone: stay indoors. Seek medical help if symptomatic."),
    (91, 100, "HAZARDOUS", "#4A0000",
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
        risk = calculate_risk(pm25=67.0, no2=31.0)
        print(risk["score"])   # 72.4
        print(risk["level"])   # HIGH
        print(risk["advice"])  # Wear N95 outdoors...
    """
    agent_list = agents or []

    # Add named args as agents
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
        thr  = WHO_THRESHOLDS[aid]
        w    = HRI_WEIGHTS.get(aid, 0)
        risk = min(1.0, float(val) / thr)
        contrib = risk * w
        raw += contrib
        breakdown[aid] = {
            "value":          val,
            "threshold":      thr,
            "normalizedRisk": round(risk, 4),
            "contribution":   round(contrib, 4),
            "exceedsWho":     float(val) > thr
        }

    score = round(min(100.0, raw * 100 * d_factor * v_factor), 2)
    level = color = advice = sadv = "CLEAN"
    for lo, hi, ln, lc, la, lsa in RISK_LEVELS:
        if lo <= score <= hi:
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

    Example:
        record = write_bxp("accra.bxp.json", {
            "latitude": 5.6037,
            "longitude": -0.1870,
            "pm25": 47.2,
            "no2": 18.3,
            "temp": 29.0,
            "humidity": 78.0
        })
    """
    dev_uuid = device_uuid or str(uuid.uuid4())
    now_us   = int(time.time() * 1_000_000)

    lat = data.get("latitude")
    lon = data.get("longitude")

    # Compute geohash if not provided
    geohash = data.get("geohash")
    if not geohash and lat and lon:
        geohash = encode_geohash(lat, lon, 7)

    # Build agents list from shorthand keys
    agents = list(data.get("agents") or [])
    shorthand = {
        "pm25": "PM2_5", "pm10": "PM10", "no2": "NO2",
        "o3": "O3",      "co": "CO",     "so2": "SO2",
        "tvoc": "TVOC",  "benz": "BENZ", "form": "FORM",
        "temp": "TEMP",  "humidity": "RH", "pressure": "PRESS",
        "uv": "UV",      "co2": "CO2",   "pm1": "PM1",
    }
    for key, aid in shorthand.items():
        if key in data and data[key] is not None:
            agents.append({
                "agentId": aid,
                "value":   float(data[key]),
                "unit":    AGENT_UNITS.get(aid, "canonical")
            })

    if not agents:
        raise ValueError("At least one agent or measurement value is required")

    # Calculate HRI
    hri = calculate_risk(agents=agents)

    record = {
        "bxpVersion":    BXP_VERSION,
        "deviceUuid":    dev_uuid,
        "geohash":       geohash,
        "latitude":      lat,
        "longitude":     lon,
        "timestampUs":   data.get("timestampUs", now_us),
        "durationS":     data.get("durationS", 60),
        "indoorOutdoor": data.get("indoorOutdoor", "outdoor"),
        "agents":        agents,
        "context":       data.get("context"),
        "quality": {
            "flag":       "UNVALIDATED",
            "confidence": 0.8,
            "qcMethod":   "client-generated"
        },
        "bxpHri":      hri["score"],
        "bxpHriLevel": hri["level"],
        "bxpHriColor": hri["color"],
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    }

    # Compute payload hash
    payload_str = json.dumps(
        {k: v for k, v in record.items() if k != "payloadHash"},
        sort_keys=True, separators=(',', ':'), default=str
    )
    record["payloadHash"] = "sha256:" + hashlib.sha256(
        payload_str.encode()
    ).hexdigest()

    Path(path).write_text(
        json.dumps(record, indent=2, default=str),
        encoding="utf-8"
    )
    return record


def read_bxp(path: Union[str, Path]) -> dict:
    """
    Read and parse a .bxp.json file.

    Args:
        path: Path to .bxp.json file

    Returns:
        Parsed BXP record dict with integrity check result

    Example:
        data = read_bxp("accra.bxp.json")
        print(data["bxpHri"])        # 61.2
        print(data["bxpHriLevel"])   # HIGH
        print(data["_integrityOk"])  # True
    """
    content = Path(path).read_text(encoding="utf-8")
    record  = json.loads(content)

    # Verify payload hash
    claimed_hash = record.get("payloadHash", "")
    check_record = {k: v for k, v in record.items()
                    if k != "payloadHash"}
    payload_str = json.dumps(
        check_record, sort_keys=True,
        separators=(',', ':'), default=str
    )
    computed = "sha256:" + hashlib.sha256(
        payload_str.encode()
    ).hexdigest()

    record["_integrityOk"]    = (computed == claimed_hash)
    record["_filePath"]       = str(path)
    record["_readAt"]         = datetime.now(timezone.utc).isoformat()

    # Re-calculate HRI for display
    agents = record.get("agents", [])
    if agents:
        hri = calculate_risk(agents=agents)
        record["_hriRecalculated"] = hri

    return record


def validate_bxp(path: Union[str, Path]) -> dict:
    """
    Validate a .bxp.json file against the BXP v2.0 spec.

    Returns dict with:
        valid (bool), errors (list), warnings (list), summary (str)
    """
    errors   = []
    warnings = []

    try:
        record = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as e:
        return {
            "valid": False,
            "errors": [f"Cannot parse file: {e}"],
            "warnings": [],
            "summary": "INVALID — Cannot parse JSON"
        }

    # Required fields
    for field in ["bxpVersion", "deviceUuid", "geohash",
                  "timestampUs", "agents"]:
        if field not in record or record[field] is None:
            errors.append(f"Missing required field: {field}")

    # Geohash precision
    gh = record.get("geohash", "")
    if gh and len(gh) < 5:
        errors.append(
            f"Geohash precision too low: {len(gh)} (minimum 5)"
        )

    # Agents
    agents = record.get("agents", [])
    if not agents:
        errors.append("No agents present")
    else:
        for i, a in enumerate(agents):
            if "agentId" not in a:
                errors.append(f"Agent {i}: missing agentId")
            if "value" not in a:
                errors.append(f"Agent {i}: missing value")

    # Timestamp
    ts = record.get("timestampUs", 0)
    now_us  = int(time.time() * 1_000_000)
    max_old = now_us - 30 * 86400 * 1_000_000
    if ts > now_us + 3600 * 1_000_000:
        warnings.append("Timestamp is in the future")
    if ts < max_old:
        warnings.append("Timestamp is older than 30 days")

    # Payload hash
    claimed = record.get("payloadHash", "")
    if claimed:
        check = {k: v for k, v in record.items()
                 if k not in ("payloadHash",)}
        payload_str = json.dumps(
            check, sort_keys=True, separators=(',', ':'), default=str
        )
        computed = "sha256:" + hashlib.sha256(
            payload_str.encode()
        ).hexdigest()
        if computed != claimed:
            errors.append("Payload hash mismatch — file may be tampered")
    else:
        warnings.append("No payloadHash — integrity unverifiable")

    # BXP version
    ver = record.get("bxpVersion", "")
    if ver != "2.0":
        warnings.append(f"bxpVersion is '{ver}', expected '2.0'")

    valid = len(errors) == 0
    if valid and not warnings:
        summary = f"VALID BXP v{ver} — {len(agents)} agent(s) — HRI {record.get('bxpHri', 'N/A')}"
    elif valid:
        summary = f"VALID with {len(warnings)} warning(s)"
    else:
        summary = f"INVALID — {len(errors)} error(s)"

    return {
        "valid":    valid,
        "errors":   errors,
        "warnings": warnings,
        "summary":  summary,
        "record":   record
    }


# ─────────────────────────────────────────────────────────────
# HTTP CLIENT
# ─────────────────────────────────────────────────────────────

class BXPClient:
    """
    BXP HTTP client for submitting readings to a BXP server.

    Example:
        client = BXPClient("http://localhost:8000",
                           device_token="bxp_device_abc123")
        result = client.submit(
            latitude=5.6037, longitude=-0.1870,
            pm25=47.2, no2=18.3, temp=29.0
        )
        print(result["bxpHri"])   # 61.2
        print(result["level"])    # HIGH
    """

    def __init__(self, base_url: str,
                 device_token: Optional[str] = None,
                 device_uuid: Optional[str] = None):
        self.base_url     = base_url.rstrip("/")
        self.device_token = device_token
        self.device_uuid  = device_uuid or str(uuid.uuid4())

    def _request(self, method: str, path: str,
                 body: Optional[dict] = None) -> dict:
        url = f"{self.base_url}{path}"
        data = json.dumps(body).encode() if body else None
        headers = {"Content-Type": "application/json"}
        if self.device_token:
            headers["Authorization"] = f"Bearer {self.device_token}"

        req = urllib.request.Request(
            url, data=data, headers=headers, method=method
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            return json.loads(e.read().decode())

    def health(self) -> dict:
        """Check server health."""
        return self._request("GET", "/bxp/v2/health")

    def submit(self, latitude: float, longitude: float,
               pm25:     Optional[float] = None,
               pm10:     Optional[float] = None,
               no2:      Optional[float] = None,
               o3:       Optional[float] = None,
               co:       Optional[float] = None,
               so2:      Optional[float] = None,
               temp:     Optional[float] = None,
               humidity: Optional[float] = None,
               agents:   Optional[list]  = None,
               **kwargs) -> dict:
        """
        Submit a reading to the BXP server.

        Returns the server's response including readingId,
        bxpHri, and bxpHriLevel.
        """
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
            "deviceUuid":  self.device_uuid,
            "latitude":    latitude,
            "longitude":   longitude,
            "timestampUs": int(time.time() * 1_000_000),
            "agents":      agent_list,
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
        return {"success": False, "error": resp.get("errors")}

    def get_readings(self, geohash: Optional[str] = None,
                     limit: int = 50) -> list:
        """Fetch readings from the server."""
        qs = f"?limit={limit}"
        if geohash:
            qs += f"&geohash={geohash}"
        resp = self._request("GET", f"/bxp/v2/readings{qs}")
        return resp.get("data", {}).get("readings", [])

    def get_latest(self, geohash: str) -> Optional[dict]:
        """Get latest reading for a geohash location."""
        resp = self._request("GET",
                             f"/bxp/v2/locations/{geohash}/latest")
        if resp.get("status") == "ok":
            return resp.get("data")
        return None
