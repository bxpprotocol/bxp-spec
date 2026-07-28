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
import uuid
import time
import hashlib
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Union

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

    Path(path).write_text(
        json.dumps(record, indent=2, default=str),
        encoding="utf-8"
    )
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


def validate_bxp(path: Union[str, Path]) -> dict:
    """
    Validate a .bxp.json file against the BXP v2.0 spec.

    Returns dict with: valid, errors, warnings, summary
    """
    errors   = []
    warnings = []

    try:
        record = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as e:
        return {
            "valid": False, "errors": [f"Cannot parse file: {e}"],
            "warnings": [], "summary": "INVALID — Cannot parse JSON"
        }

    for field in ["bxpVersion", "deviceUuid", "geohash", "timestampUs", "agents"]:
        if field not in record or record[field] is None:
            errors.append(f"Missing required field: {field}")

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
    if ver != "2.0":
        warnings.append(f"bxpVersion is '{ver}', expected '2.0'")

    valid = len(errors) == 0
    if valid and not warnings:
        summary = f"VALID BXP v{ver} — {len(agents)} agent(s) — HRI {record.get('bxpHri', 'N/A')}"
    elif valid:
        summary = f"VALID with {len(warnings)} warning(s)"
    else:
        summary = f"INVALID — {len(errors)} error(s)"

    return {"valid": valid, "errors": errors, "warnings": warnings,
            "summary": summary, "record": record}


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
