"""
BXP Protocol Reference Node v2.1
Real-time global atmospheric exposure data
Powered by AQICN + BXP standard format

Improvements over v2.0:
  - SQLite persistence (no data loss on restart)
  - Device token authentication (Bearer tokens validated)
  - POST /readings returns 201
  - HRI includes duration + population factors
  - Full input validation (lat/lon range, negative checks)
  - Rate limiting (per-IP sliding window)
  - Structured logging
  - Cursor/offset pagination
  - Background city preload on startup
  - AQICN fallback with clear error messages
  - ETag / If-None-Match caching headers
  - DELETE /readings/{id} with cryptographic proof
  - GET /readings/{id}/verify — integrity check
  - GET /locations/{geohash}/aggregate — k≥5 anonymity
  - POST/GET /community/reports
  - POST /devices/register, GET /devices/{uuid}
  - GET /search
  - GET /nodes — federated node discovery
  - GET /metrics — Prometheus format
  - GET /widget/{city} — embeddable iframe widget
  - Dashboard: map, chart, comparison, auto-refresh, export
"""

from fastapi import FastAPI, HTTPException, Request, Response, Depends, Header
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator
from typing import Optional, List
import httpx
import asyncio
import json
import time
import hashlib
import uuid
import logging
import os
from datetime import datetime, timezone
import uvicorn

from database import (
    init_db, insert_reading, get_reading, delete_reading, verify_reading,
    query_readings, get_geohash_latest, get_geohash_history, get_aggregate,
    reading_count, register_device, get_device, validate_token,
    bump_device_seen, insert_report, query_reports,
    upsert_node, get_nodes,
)

# ─── Logging ──────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
log = logging.getLogger("bxp.server")

# ─── Config ───────────────────────────────────────────────────
AQICN_TOKEN  = os.environ.get("AQICN_TOKEN", "")
BXP_VERSION  = "2.0"
NODE_ID      = os.environ.get("BXP_NODE_ID", "bxp-public-node-001")
NODE_TYPE    = os.environ.get("BXP_NODE_TYPE", "reference")

# ─── Agent ID normalisation ───────────────────────────────────
AGENT_ID_MAP = {
    "PM2_5": "pm25", "PM10": "pm10", "NO2": "no2",
    "O3":    "o3",   "CO":   "co",   "SO2": "so2",
}

WHO_THRESHOLDS = {
    "pm25": 15.0, "pm10": 45.0, "no2": 25.0,
    "o3": 100.0, "co": 4.0, "so2": 40.0
}

WEIGHTS = {
    "pm25": 0.35, "pm10": 0.15, "no2": 0.15,
    "o3": 0.12, "co": 0.10, "so2": 0.05
}

# ─── Pydantic models ──────────────────────────────────────────

class AgentReading(BaseModel):
    agentId: str
    value:   float
    unit:    Optional[str] = None

    @field_validator("value")
    @classmethod
    def value_non_negative(cls, v):
        if v < 0:
            raise ValueError("agent value must be non-negative")
        return v


class RawReading(BaseModel):
    deviceUuid:   Optional[str]  = None
    latitude:     float
    longitude:    float
    timestampUs:  Optional[int]  = None
    agents:       List[AgentReading] = []
    durationS:    Optional[int]  = 60
    indoorOutdoor: Optional[str] = "outdoor"

    @field_validator("latitude")
    @classmethod
    def lat_range(cls, v):
        if not -90 <= v <= 90:
            raise ValueError("latitude must be between -90 and 90")
        return v

    @field_validator("longitude")
    @classmethod
    def lon_range(cls, v):
        if not -180 <= v <= 180:
            raise ValueError("longitude must be between -180 and 180")
        return v


class SubmitReadingsRequest(BaseModel):
    readings: List[RawReading]


class DeviceRegisterRequest(BaseModel):
    deviceUuid: Optional[str] = None
    label:      Optional[str] = None
    ownerHash:  Optional[str] = None   # pre-hashed owner ID for privacy


class CommunityReportRequest(BaseModel):
    latitude:    float
    longitude:   float
    reportType:  str = "observation"
    description: Optional[str] = None
    severity:    Optional[str] = None
    submitterHash: Optional[str] = None  # SHA-256 hashed person ID (§9)

    @field_validator("latitude")
    @classmethod
    def lat_range(cls, v):
        if not -90 <= v <= 90:
            raise ValueError("latitude must be between -90 and 90")
        return v

    @field_validator("longitude")
    @classmethod
    def lon_range(cls, v):
        if not -180 <= v <= 180:
            raise ValueError("longitude must be between -180 and 180")
        return v


# ─── Rate limiter ─────────────────────────────────────────────

class RateLimiter:
    """Sliding-window rate limiter — in-memory per-IP."""
    def __init__(self, calls: int, window_s: int):
        self._calls  = calls
        self._window = window_s
        self._store: dict[str, list] = {}
        self._lock = asyncio.Lock()

    async def check(self, key: str) -> bool:
        async with self._lock:
            now = time.time()
            window_start = now - self._window
            hist = self._store.get(key, [])
            hist = [t for t in hist if t > window_start]
            if len(hist) >= self._calls:
                return False
            hist.append(now)
            self._store[key] = hist
            return True

    def reset(self):
        """Clear all rate-limit state (useful in tests)."""
        self._store.clear()


_rl_submit   = RateLimiter(30,  60)   # 30 submissions / minute
_rl_city     = RateLimiter(60,  60)   # 60 city lookups / minute
_rl_register = RateLimiter(5,   60)   # 5 device registrations / minute


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# ─── HRI calculation ──────────────────────────────────────────

def calculate_hri(
    readings: dict,
    duration: str = "1h",
    population: str = "general",
) -> float:
    """
    Calculate BXP_HRI with duration and population factors.
    duration:   "1h" | "8h" | "24h"
    population: "general" | "sensitive"
    """
    d_factor = {"1h": 1.0, "8h": 1.2, "24h": 1.5}.get(duration, 1.0)
    v_factor = {"general": 1.0, "sensitive": 1.3}.get(population, 1.0)
    score = 0.0
    for agent, weight in WEIGHTS.items():
        val = readings.get(agent)
        thresh = WHO_THRESHOLDS.get(agent)
        if val is not None and thresh:
            normalized = min(float(val) / thresh, 1.0)
            score += normalized * weight
    return round(min(score * 100 * d_factor * v_factor, 100), 1)


def hri_level(hri: float) -> str:
    if hri <= 20: return "CLEAN"
    if hri <= 40: return "MODERATE"
    if hri <= 60: return "ELEVATED"
    if hri <= 75: return "HIGH"
    if hri <= 90: return "VERY_HIGH"
    return "HAZARDOUS"


def hri_color(hri: float) -> str:
    if hri <= 20: return "#00E676"
    if hri <= 40: return "#FFEB3B"
    if hri <= 60: return "#FF9800"
    if hri <= 75: return "#F44336"
    if hri <= 90: return "#9C27B0"
    return "#4A0000"


def hri_advice(level: str) -> str:
    return {
        "CLEAN":     "Air quality is excellent. Enjoy outdoor activities freely.",
        "MODERATE":  "Air quality is acceptable. Sensitive individuals should limit prolonged outdoor exertion.",
        "ELEVATED":  "Sensitive groups should reduce prolonged outdoor exertion.",
        "HIGH":      "Everyone should reduce prolonged outdoor exertion. Sensitive groups stay indoors.",
        "VERY_HIGH": "Avoid outdoor activities. Sensitive groups must stay indoors.",
        "HAZARDOUS": "Health emergency. Everyone should avoid all outdoor activity.",
    }.get(level, "")


def assess_quality(agents_dict: dict, timestamp_us: int) -> dict:
    notes = []
    now_us = int(time.time() * 1_000_000)

    if not agents_dict:
        return {"flag": "INVALID", "confidence": 0.0,
                "qcMethod": "server-auto", "notes": ["No agents present"]}

    if timestamp_us > now_us + 3_600_000_000:
        notes.append("Timestamp is in the future")
        return {"flag": "SUSPECT", "confidence": 0.3,
                "qcMethod": "server-auto", "notes": notes}

    any_exceeds = critical = False
    for key, val in agents_dict.items():
        if val is None:
            continue
        thr = WHO_THRESHOLDS.get(key)
        if thr is None:
            continue
        if float(val) > thr:
            any_exceeds = True
        if float(val) > thr * 5:
            critical = True
            notes.append(f"{key}={val} exceeds 5× WHO threshold ({thr})")

    if critical:
        return {"flag": "SUSPECT", "confidence": 0.4,
                "qcMethod": "server-auto", "notes": notes}

    confidence = 0.75 if any_exceeds else 0.90
    return {"flag": "UNVALIDATED", "confidence": confidence,
            "qcMethod": "server-auto", "notes": notes or None}


def _encode_geohash(lat: float, lon: float, precision: int = 7) -> str:
    BASE32 = "0123456789bcdefghjkmnpqrstuvwxyz"
    lat_r, lon_r = [-90.0, 90.0], [-180.0, 180.0]
    bits = [16, 8, 4, 2, 1]
    bi, even, result, ch = 0, True, "", 0
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
        bi += 1
        if bi == 5:
            result += BASE32[ch]; ch = 0; bi = 0
    return result


# ─── AQICN cache ──────────────────────────────────────────────
_city_cache:   dict = {}
_city_ts:      dict = {}
CACHE_TTL = 600   # 10 min


async def fetch_city_data(city: str) -> Optional[dict]:
    key = city.lower().strip()
    now = time.time()

    if key in _city_cache and (now - _city_ts.get(key, 0)) < CACHE_TTL:
        return _city_cache[key]

    if not AQICN_TOKEN:
        return {
            "_noToken": True,
            "error": "AQICN_TOKEN not configured. "
                     "Set the AQICN_TOKEN environment variable to enable "
                     "live city data. Get a free token at https://aqicn.org/api/",
        }

    url = f"https://api.waqi.info/feed/{city}/?token={AQICN_TOKEN}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()

        if data.get("status") != "ok":
            log.warning("AQICN returned non-ok for city=%s: %s", city, data)
            return None

        d    = data["data"]
        iaqi = d.get("iaqi", {})

        readings = {
            "pm25": iaqi.get("pm25", {}).get("v"),
            "pm10": iaqi.get("pm10", {}).get("v"),
            "no2":  iaqi.get("no2",  {}).get("v"),
            "o3":   iaqi.get("o3",   {}).get("v"),
            "co":   iaqi.get("co",   {}).get("v"),
            "so2":  iaqi.get("so2",  {}).get("v"),
        }

        hri   = calculate_hri(readings)
        level = hri_level(hri)

        city_name = d.get("city", {}).get("name", city)
        geo       = d.get("city", {}).get("geo", [0, 0])

        bxp_record = {
            "bxp_version": BXP_VERSION,
            "record_id":   hashlib.sha256(
                f"{city_name}{time.time()}".encode()
            ).hexdigest()[:16],
            "node_id":     NODE_ID,
            "timestamp":   datetime.now(timezone.utc).isoformat(),
            "location": {
                "name":      city_name,
                "query":     city,
                "latitude":  geo[0] if len(geo) > 0 else None,
                "longitude": geo[1] if len(geo) > 1 else None,
            },
            "readings":  {k: v for k, v in readings.items() if v is not None},
            "bxp_hri": {
                "score":  hri,
                "level":  level,
                "color":  hri_color(hri),
                "advice": hri_advice(level),
            },
            "source":              "AQICN",
            "aqi":                 d.get("aqi"),
            "dominant_pollutant":  d.get("dominentpol"),
            "attribution":
                d.get("attributions", [{}])[0].get("name", "AQICN")
                if d.get("attributions") else "AQICN",
        }

        # ETag from content hash
        etag = '"' + hashlib.md5(
            json.dumps(bxp_record, sort_keys=True, default=str).encode()
        ).hexdigest() + '"'
        bxp_record["_etag"] = etag

        _city_cache[key] = bxp_record
        _city_ts[key]    = now
        log.info("Fetched city data city=%s hri=%.1f", city, hri)
        return bxp_record

    except httpx.HTTPStatusError as e:
        log.warning("AQICN HTTP error city=%s status=%s", city, e.response.status_code)
        return None
    except Exception as e:
        log.error("AQICN fetch error city=%s: %s", city, e)
        return None


# ─── Default cities ───────────────────────────────────────────
DEFAULT_CITIES = [
    "accra", "lagos", "delhi", "beijing", "london",
    "sao paulo", "new york", "nairobi", "jakarta", "cairo",
]


# ─── FastAPI app ──────────────────────────────────────────────

SERVER_START_TIME = time.time()

app = FastAPI(
    title="BXP Protocol Node",
    description="Open standard for atmospheric exposure data — https://github.com/bxpprotocol/bxp-spec",
    version="2.1.0",
    docs_url="/docs",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["ETag"],
)


@app.on_event("startup")
async def startup():
    init_db()
    log.info("BXP Node starting — node_id=%s", NODE_ID)
    # Background preload of default cities
    if AQICN_TOKEN:
        asyncio.create_task(_preload_cities())
    else:
        log.warning(
            "AQICN_TOKEN not set — live city data disabled. "
            "Set via environment variable to enable."
        )


async def _preload_cities():
    """Warm the cache on startup so first requests are fast."""
    log.info("Preloading %d default cities…", len(DEFAULT_CITIES))
    tasks = [fetch_city_data(c) for c in DEFAULT_CITIES]
    await asyncio.gather(*tasks, return_exceptions=True)
    log.info("City preload complete")


# ─── Routes ───────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def root():
    return HTMLResponse(LANDING_PAGE)


@app.get("/bxp/v2/health")
async def health():
    uptime_s = int(time.time() - SERVER_START_TIME)
    h, r = divmod(uptime_s, 3600)
    m, s = divmod(r, 60)
    cnt = reading_count()
    return {
        "status":      "ok",
        "bxpVersion":  BXP_VERSION,
        "nodeId":      NODE_ID,
        "nodeType":    NODE_TYPE,
        "timestamp":   datetime.now(timezone.utc).isoformat(),
        "uptime":      f"{h}h {m}m {s}s",
        "readingCount": cnt,
        "cachedLocations": len(_city_cache),
        "aqicnEnabled": bool(AQICN_TOKEN),
        "data": {
            "bxpVersion":  BXP_VERSION,
            "nodeType":    NODE_TYPE,
            "readingCount": cnt,
            "uptime":      f"{h}h {m}m {s}s",
        },
        "spec": "https://github.com/bxpprotocol/bxp-spec",
        "doi":  "https://doi.org/10.5281/zenodo.18906812",
    }


# ─── City lookup ──────────────────────────────────────────────

@app.get("/bxp/v2/city/{city}")
async def get_city(city: str, request: Request, response: Response):
    ip = _client_ip(request)
    if not await _rl_city.check(ip):
        raise HTTPException(status_code=429,
                            detail="Rate limit exceeded — 60 requests/minute")

    data = await fetch_city_data(city)
    if not data:
        raise HTTPException(
            status_code=404,
            detail=f"No data found for '{city}'. Try a different city name."
        )
    if data.get("_noToken"):
        raise HTTPException(
            status_code=503,
            detail=data["error"]
        )

    # ETag support
    etag = data.get("_etag", "")
    if etag:
        response.headers["ETag"] = etag
        if_none_match = request.headers.get("if-none-match", "")
        if if_none_match == etag:
            return Response(status_code=304)

    clean = {k: v for k, v in data.items() if not k.startswith("_")}
    return clean


# ─── Readings collection ──────────────────────────────────────

@app.get("/bxp/v2/readings")
async def get_readings(
    geohash:  Optional[str] = None,
    from_ts:  Optional[int] = None,
    to_ts:    Optional[int] = None,
    agent:    Optional[str] = None,
    quality:  Optional[str] = None,
    limit:    int = 50,
    offset:   int = 0,
):
    """
    List readings with cursor/offset pagination.
    When no filters given, returns live data for default cities.
    """
    limit = min(limit, 200)

    if any([geohash, from_ts, to_ts, agent, quality]):
        results, total = query_readings(
            geohash=geohash, from_ts=from_ts, to_ts=to_ts,
            agent=agent, quality=quality,
            limit=limit, offset=offset,
        )
        return {
            "status": "ok",
            "count":  len(results),
            "total":  total,
            "offset": offset,
            "limit":  limit,
            "data":   {"readings": results},
        }

    # Default: live city data
    results = []
    for city in DEFAULT_CITIES:
        data = await fetch_city_data(city)
        if data and not data.get("_noToken"):
            results.append({k: v for k, v in data.items()
                            if not k.startswith("_")})

    if not results and not AQICN_TOKEN:
        return {
            "status": "ok",
            "count":  0,
            "data":   {"readings": []},
            "notice": "AQICN_TOKEN not set. "
                      "Set this environment variable to see live global data.",
        }

    return {"status": "ok", "count": len(results),
            "data": {"readings": results}}


@app.get("/bxp/v2/readings/{reading_id}")
async def get_reading_by_id(reading_id: str):
    rec = get_reading(reading_id)
    if not rec:
        raise HTTPException(status_code=404,
                            detail=f"Reading '{reading_id}' not found.")
    return {"status": "ok", "data": {"reading": rec}}


@app.post("/bxp/v2/readings", status_code=201)
async def submit_readings(
    body: SubmitReadingsRequest,
    request: Request,
    authorization: Optional[str] = Header(None),
):
    """Accept BXP readings submitted by SDK clients or devices. Returns 201."""
    ip = _client_ip(request)
    if not await _rl_submit.check(ip):
        raise HTTPException(status_code=429,
                            detail="Rate limit exceeded — 30 submissions/minute")

    if not body.readings:
        raise HTTPException(status_code=400, detail="No readings provided.")

    # Token auth (optional — anonymous submissions are allowed but marked)
    authed_device: Optional[str] = None
    if authorization:
        token = authorization.removeprefix("Bearer ").strip()
        authed_device = validate_token(token)
        if not authed_device:
            raise HTTPException(
                status_code=401,
                detail="Invalid or expired device token."
            )

    processed = []
    for raw in body.readings:
        readings_dict: dict = {}
        for agent in raw.agents:
            key = AGENT_ID_MAP.get(agent.agentId.upper())
            if key:
                readings_dict[key] = agent.value

        duration   = "1h"
        population = "general"
        if raw.durationS:
            if raw.durationS >= 86400:
                duration = "24h"
            elif raw.durationS >= 28800:
                duration = "8h"

        hri   = calculate_hri(readings_dict, duration, population)
        level = hri_level(hri)

        ts_us = raw.timestampUs or int(time.time() * 1_000_000)

        device_uuid = (authed_device or raw.deviceUuid
                       or str(uuid.uuid4()))
        reading_id = hashlib.sha256(
            f"{device_uuid}{ts_us}".encode()
        ).hexdigest()[:16]

        geohash = _encode_geohash(raw.latitude, raw.longitude)
        # §9: geohash floor — never store precision < 5 for personal records
        geohash = geohash[:max(5, len(geohash))]

        quality = assess_quality(readings_dict, ts_us)

        # Privacy: floor geohash to precision 5 if no auth (§9)
        stored_geohash = geohash[:5] if not authed_device else geohash

        record = {
            "readingId":    reading_id,
            "bxpVersion":   BXP_VERSION,
            "nodeId":       NODE_ID,
            "deviceUuid":   device_uuid,
            "timestamp":    datetime.now(timezone.utc).isoformat(),
            "timestampUs":  ts_us,
            "latitude":     raw.latitude,
            "longitude":    raw.longitude,
            "geohash":      stored_geohash,
            "location": {
                "latitude":  raw.latitude,
                "longitude": raw.longitude,
                "geohash":   stored_geohash,
            },
            "readings":     readings_dict,
            "agents":       [a.model_dump() for a in raw.agents],
            "bxpHri":       hri,
            "bxpHriLevel":  level,
            "quality":      quality,
            "qualityFlag":  quality["flag"],
            "durationS":    raw.durationS,
            "indoorOutdoor": raw.indoorOutdoor,
        }

        # Payload hash for integrity verification (§2.2)
        payload_str = json.dumps(
            {k: v for k, v in record.items() if k != "payloadHash"},
            sort_keys=True, separators=(',', ':'), default=str
        )
        record["payloadHash"] = "sha256:" + hashlib.sha256(
            payload_str.encode()
        ).hexdigest()

        insert_reading(record)
        if authed_device:
            bump_device_seen(authed_device, ts_us)

        processed.append(record)
        log.info(
            "Reading submitted id=%s hri=%.1f quality=%s device=%s",
            reading_id, hri, quality["flag"], device_uuid
        )

    return {"status": "ok", "data": {"readings": processed}}


@app.delete("/bxp/v2/readings/{reading_id}")
async def delete_reading_endpoint(
    reading_id: str,
    authorization: Optional[str] = Header(None),
):
    """
    Delete a reading with cryptographic proof (§9).
    Authentication required.
    """
    if not authorization:
        raise HTTPException(status_code=401,
                            detail="Authorization header required for deletion.")
    token = authorization.removeprefix("Bearer ").strip()
    authed = validate_token(token)
    if not authed:
        raise HTTPException(status_code=401,
                            detail="Invalid or expired device token.")

    proof = delete_reading(reading_id)
    if proof is None:
        raise HTTPException(status_code=404,
                            detail=f"Reading '{reading_id}' not found.")

    log.info("Reading deleted id=%s proof=%s", reading_id, proof)
    return {
        "status":       "ok",
        "readingId":    reading_id,
        "deleted":      True,
        "deletionProof": proof,
        "message":      "Reading cryptographically deleted per BXP §9.",
    }


@app.get("/bxp/v2/readings/{reading_id}/verify")
async def verify_reading_endpoint(reading_id: str):
    """Verify integrity of a reading using its stored payloadHash (§2.2)."""
    result = verify_reading(reading_id)
    if not result:
        raise HTTPException(status_code=404,
                            detail=f"Reading '{reading_id}' not found.")
    return {"status": "ok", "data": result}


# ─── Location endpoints ───────────────────────────────────────

@app.get("/bxp/v2/locations/{geohash}/latest")
async def get_location_latest(geohash: str):
    if len(geohash) < 5:
        raise HTTPException(status_code=400,
                            detail="Geohash precision must be at least 5.")
    rec = get_geohash_latest(geohash)
    if not rec:
        raise HTTPException(status_code=404,
                            detail=f"No readings for geohash '{geohash}'.")
    return {"status": "ok", "data": {"reading": rec, "bxpHri": rec["bxpHri"]}}


@app.get("/bxp/v2/locations/{geohash}/history")
async def get_location_history(geohash: str, limit: int = 50):
    if len(geohash) < 5:
        raise HTTPException(status_code=400,
                            detail="Geohash precision must be at least 5.")
    records = get_geohash_history(geohash, min(limit, 200))
    return {"status": "ok", "count": len(records),
            "data": {"readings": records}}


@app.get("/bxp/v2/locations/{geohash}/aggregate")
async def get_location_aggregate(
    geohash: str,
    from_ts: Optional[int] = None,
    to_ts:   Optional[int] = None,
):
    """
    Privacy-safe aggregate endpoint (§9).
    Returns min/max/avg HRI only when ≥5 readings exist (k-anonymity).
    """
    if len(geohash) < 5:
        raise HTTPException(status_code=400,
                            detail="Geohash precision must be at least 5.")
    agg = get_aggregate(geohash, from_ts, to_ts)
    if not agg:
        raise HTTPException(
            status_code=404,
            detail="Insufficient data. Aggregate requires ≥5 readings (k-anonymity §9)."
        )
    return {"status": "ok", "data": agg}


# ─── Search ───────────────────────────────────────────────────

@app.get("/bxp/v2/search")
async def search(
    q:      Optional[str]   = None,
    lat:    Optional[float] = None,
    lon:    Optional[float] = None,
    radius: Optional[float] = None,   # km, not yet spatial — returns nearby geohash
    limit:  int = 20,
):
    """Search for readings by city name or coordinates (§5)."""
    results = []

    # Name-based search → AQICN
    if q:
        city_data = await fetch_city_data(q)
        if city_data and not city_data.get("_noToken"):
            results.append({k: v for k, v in city_data.items()
                            if not k.startswith("_")})

    # Coordinate-based search → submitted readings
    if lat is not None and lon is not None:
        gh = _encode_geohash(lat, lon, 5)
        db_results, _ = query_readings(geohash=gh, limit=limit)
        results.extend(db_results)

    if not results:
        return {"status": "ok", "count": 0, "data": {"results": []}}

    return {
        "status":  "ok",
        "count":   len(results),
        "data":    {"results": results[:limit]},
    }


# ─── Community reports ────────────────────────────────────────

@app.post("/bxp/v2/community/reports", status_code=201)
async def submit_report(body: CommunityReportRequest, request: Request):
    ip = _client_ip(request)
    if not await _rl_submit.check(ip):
        raise HTTPException(status_code=429,
                            detail="Rate limit exceeded.")

    report_id = hashlib.sha256(
        f"{body.latitude}{body.longitude}{time.time()}".encode()
    ).hexdigest()[:16]
    gh = _encode_geohash(body.latitude, body.longitude, 5)  # floor to 5 (§9)

    report = {
        "reportId":     report_id,
        "geohash":      gh,
        "latitude":     body.latitude,
        "longitude":    body.longitude,
        "timestamp":    datetime.now(timezone.utc).isoformat(),
        "timestampUs":  int(time.time() * 1_000_000),
        "reportType":   body.reportType,
        "description":  body.description,
        "severity":     body.severity,
        "submitterHash": body.submitterHash,
    }
    insert_report(report)
    log.info("Community report submitted id=%s type=%s",
             report_id, body.reportType)
    return {"status": "ok", "data": {"report": report}}


@app.get("/bxp/v2/community/reports")
async def get_reports(geohash: Optional[str] = None, limit: int = 50):
    reports = query_reports(geohash, min(limit, 200))
    return {"status": "ok", "count": len(reports),
            "data": {"reports": reports}}


# ─── Device registration ──────────────────────────────────────

@app.post("/bxp/v2/devices/register", status_code=201)
async def register_device_endpoint(
    body: DeviceRegisterRequest,
    request: Request,
):
    ip = _client_ip(request)
    if not await _rl_register.check(ip):
        raise HTTPException(status_code=429,
                            detail="Rate limit exceeded — 5 registrations/minute.")

    dev_uuid = body.deviceUuid or str(uuid.uuid4())
    # Generate a random token
    raw_token = "bxp_" + uuid.uuid4().hex
    token_hash = "sha256:" + hashlib.sha256(raw_token.encode()).hexdigest()

    device = register_device(
        device_uuid=dev_uuid,
        token_hash=token_hash,
        label=body.label,
        owner_hash=body.ownerHash,
    )
    log.info("Device registered uuid=%s", dev_uuid)
    return {
        "status": "ok",
        "data":   {
            "device": device,
            "token": raw_token,   # only returned once — store securely
            "notice": "Store this token securely. It will not be shown again.",
        },
    }


@app.get("/bxp/v2/devices/{device_uuid}")
async def get_device_endpoint(device_uuid: str):
    device = get_device(device_uuid)
    if not device:
        raise HTTPException(status_code=404,
                            detail=f"Device '{device_uuid}' not found.")
    return {"status": "ok", "data": {"device": device}}


# ─── Federated nodes ──────────────────────────────────────────

@app.get("/bxp/v2/nodes")
async def list_nodes():
    """List known federated BXP nodes."""
    nodes = get_nodes(active_only=True)
    return {"status": "ok", "count": len(nodes), "data": {"nodes": nodes}}


@app.post("/bxp/v2/nodes/announce")
async def announce_node(request: Request):
    """Allow a node to announce itself to this node."""
    try:
        body = await request.json()
        node_id   = body.get("nodeId", "")
        base_url  = body.get("baseUrl", "")
        if not node_id or not base_url:
            raise HTTPException(status_code=400,
                                detail="nodeId and baseUrl required.")
        upsert_node(
            node_id=node_id,
            base_url=base_url,
            bxp_version=body.get("bxpVersion", "2.0"),
            node_type=body.get("nodeType", "unknown"),
            reading_count=body.get("readingCount", 0),
        )
        log.info("Node announced node_id=%s url=%s", node_id, base_url)
        return {"status": "ok", "message": "Node registered."}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─── Prometheus metrics ───────────────────────────────────────

@app.get("/metrics", response_class=PlainTextResponse)
async def metrics():
    """Prometheus-compatible metrics endpoint."""
    cnt = reading_count()
    uptime = time.time() - SERVER_START_TIME
    cached = len(_city_cache)
    lines = [
        "# HELP bxp_readings_total Total submitted readings (non-deleted)",
        "# TYPE bxp_readings_total counter",
        f"bxp_readings_total {cnt}",
        "",
        "# HELP bxp_uptime_seconds Server uptime in seconds",
        "# TYPE bxp_uptime_seconds gauge",
        f"bxp_uptime_seconds {uptime:.1f}",
        "",
        "# HELP bxp_city_cache_size Number of cached city responses",
        "# TYPE bxp_city_cache_size gauge",
        f"bxp_city_cache_size {cached}",
        "",
        "# HELP bxp_info BXP node information",
        "# TYPE bxp_info gauge",
        f'bxp_info{{node_id="{NODE_ID}",bxp_version="{BXP_VERSION}",node_type="{NODE_TYPE}"}} 1',
    ]
    return "\n".join(lines) + "\n"


# ─── Widget ───────────────────────────────────────────────────

@app.get("/widget/{city}", response_class=HTMLResponse)
async def widget(city: str):
    """Embeddable iframe widget for any website."""
    data = await fetch_city_data(city)
    if not data or data.get("_noToken"):
        return HTMLResponse(
            f'<html><body style="background:#060b18;color:#4a5568;'
            f'font-family:sans-serif;display:flex;align-items:center;'
            f'justify-content:center;height:100%;margin:0">'
            f'No data for "{city}"</body></html>'
        )
    hri    = data["bxp_hri"]["score"]
    level  = data["bxp_hri"]["level"]
    color  = data["bxp_hri"]["color"]
    advice = data["bxp_hri"]["advice"]
    loc    = data["location"]["name"]
    return HTMLResponse(f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:#060b18;color:#e8edf5;font-family:'Segoe UI',sans-serif;
  padding:12px;height:100%;display:flex;flex-direction:column;gap:8px}}
.loc{{font-size:13px;font-weight:700;white-space:nowrap;overflow:hidden;
  text-overflow:ellipsis;color:#94a3b8}}
.score{{font-size:42px;font-weight:800;color:{color};line-height:1;
  font-variant-numeric:tabular-nums}}
.level{{font-size:11px;font-weight:700;color:{color};letter-spacing:.1em}}
.advice{{font-size:10px;color:#4a5568;line-height:1.4;flex:1}}
.brand{{font-size:9px;color:#1a2540;text-align:right;margin-top:auto}}
.brand a{{color:#1a2540;text-decoration:none}}
</style></head>
<body>
<div class="loc">{loc}</div>
<div class="score">{hri}</div>
<div class="level">{level}</div>
<div class="advice">{advice}</div>
<div class="brand"><a href="/dashboard/{city}" target="_blank">BXP Protocol</a></div>
</body></html>""")


# ─── Dashboard routes ─────────────────────────────────────────

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_home():
    return HTMLResponse(SEARCH_PAGE)


@app.get("/map", response_class=HTMLResponse)
async def map_view():
    return HTMLResponse(MAP_PAGE)


@app.get("/compare", response_class=HTMLResponse)
async def compare_view():
    return HTMLResponse(COMPARE_PAGE)


@app.get("/dashboard/{city}", response_class=HTMLResponse)
async def dashboard(city: str):
    data = await fetch_city_data(city)
    if not data or data.get("_noToken"):
        msg = data["error"] if data and data.get("_noToken") else \
              f"No air quality data available for \"{city}\""
        return HTMLResponse(f"""<!DOCTYPE html>
<html><body style="background:#060b18;color:white;font-family:sans-serif;
display:flex;align-items:center;justify-content:center;height:100vh;
margin:0;flex-direction:column;gap:1rem">
<h1 style="font-size:2rem">Location not found</h1>
<p style="color:#4a5568;max-width:400px;text-align:center">{msg}</p>
<a href="/dashboard" style="color:#00d4ff;text-decoration:none">← Search another location</a>
</body></html>""")
    return HTMLResponse(render_dashboard(data))


# ─── Dashboard renderer ───────────────────────────────────────

def render_dashboard(data: dict) -> str:
    hri       = data["bxp_hri"]["score"]
    level     = data["bxp_hri"]["level"]
    color     = data["bxp_hri"]["color"]
    advice    = data["bxp_hri"]["advice"]
    location  = data["location"]["name"]
    readings  = data["readings"]
    timestamp = data["timestamp"]
    aqi       = data.get("aqi", "N/A")
    dominant  = (data.get("dominant_pollutant") or "").upper()
    query     = data["location"]["query"]

    try:
        r = int(color[1:3], 16)
        g = int(color[3:5], 16)
        b = int(color[5:7], 16)
        rgb = f"{r},{g},{b}"
    except Exception:
        rgb = "0,212,255"

    def reading_card(label, key, unit):
        val = readings.get(key)
        if val is None:
            return f'''<div class="r-card">
<span class="r-label">{label}</span>
<span class="r-val na">N/A</span>
<div class="r-bar-bg"><div class="r-bar" style="width:0%"></div></div>
<span class="r-who">WHO: {WHO_THRESHOLDS.get(key,"—")} {unit}</span>
</div>'''
        thresh = WHO_THRESHOLDS.get(key, 100)
        pct    = min(int((float(val) / thresh) * 100), 100)
        bar_color = "#00E676" if pct < 50 else "#FF9800" if pct < 100 else "#F44336"
        return f'''<div class="r-card">
<span class="r-label">{label}</span>
<span class="r-val">{val}<span class="r-unit"> {unit}</span></span>
<div class="r-bar-bg"><div class="r-bar" style="width:{pct}%;background:{bar_color}"></div></div>
<span class="r-who">WHO threshold: {thresh} {unit}</span>
</div>'''

    cards = "".join([
        reading_card("PM2.5", "pm25", "μg/m³"),
        reading_card("PM10",  "pm10", "μg/m³"),
        reading_card("NO₂",   "no2",  "μg/m³"),
        reading_card("O₃",    "o3",   "μg/m³"),
        reading_card("CO",    "co",   "mg/m³"),
        reading_card("SO₂",   "so2",  "μg/m³"),
    ])

    dominant_pill = f'<span class="meta-pill">Dominant: {dominant}</span>' if dominant else ""

    # JSON for export button
    export_json = json.dumps(
        {k: v for k, v in data.items() if not k.startswith("_")},
        indent=2, default=str
    ).replace("</script>", "<\\/script>")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>BXP — {location} Air Quality</title>
<link href="https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Syne:wght@400;700;800&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
:root{{
  --bg:#060b18;--surface:#0d1628;--border:#1a2540;
  --text:#e8edf5;--muted:#4a5568;--accent:#00d4ff;
  --hri:{color};--rgb:{rgb};
}}
body{{background:var(--bg);color:var(--text);font-family:'Syne',sans-serif;min-height:100vh;
  background-image:radial-gradient(ellipse at 15% 15%,rgba(0,212,255,0.03) 0%,transparent 50%),
    radial-gradient(ellipse at 85% 85%,rgba(var(--rgb),0.06) 0%,transparent 50%);}}
header{{padding:1.25rem 2rem;display:flex;align-items:center;justify-content:space-between;
  border-bottom:1px solid var(--border);background:rgba(6,11,24,0.92);backdrop-filter:blur(12px);
  position:sticky;top:0;z-index:100;}}
.logo{{font-family:'Space Mono',monospace;font-size:0.9rem;color:var(--accent);letter-spacing:0.15em}}
nav a{{color:var(--muted);text-decoration:none;margin-left:1.5rem;font-size:0.82rem;transition:color 0.2s}}
nav a:hover{{color:var(--accent)}}
.main{{max-width:1100px;margin:0 auto;padding:3rem 2rem}}
.loc{{font-size:clamp(2rem,5vw,3.5rem);font-weight:800;letter-spacing:-0.02em;line-height:1;margin-bottom:0.4rem}}
.ts-row{{display:flex;align-items:center;gap:1rem;margin-bottom:2.5rem;flex-wrap:wrap}}
.ts{{font-family:'Space Mono',monospace;font-size:0.7rem;color:var(--muted)}}
.refresh-badge{{font-family:'Space Mono',monospace;font-size:0.65rem;color:#00E676;
  background:rgba(0,230,118,0.08);border:1px solid rgba(0,230,118,0.2);
  padding:0.2rem 0.6rem;border-radius:999px;cursor:pointer;transition:all 0.2s}}
.refresh-badge:hover{{background:rgba(0,230,118,0.15)}}
.hri-block{{background:var(--surface);border:1px solid var(--border);border-radius:1.5rem;
  padding:2.5rem;margin-bottom:2rem;display:grid;grid-template-columns:auto 1fr;gap:3rem;
  align-items:center;position:relative;overflow:hidden;}}
.hri-block::after{{content:'';position:absolute;top:0;left:0;right:0;height:3px;background:var(--hri);}}
.score{{font-size:clamp(4rem,10vw,6.5rem);font-weight:800;font-family:'Space Mono',monospace;
  color:var(--hri);line-height:1;text-shadow:0 0 60px rgba(var(--rgb),0.4);}}
.level{{font-size:1.4rem;font-weight:700;color:var(--hri);margin-bottom:0.6rem;letter-spacing:0.05em}}
.advice{{font-size:0.95rem;color:#94a3b8;line-height:1.65;margin-bottom:1rem;max-width:480px}}
.pills{{display:flex;gap:0.75rem;flex-wrap:wrap;align-items:center}}
.meta-pill{{font-family:'Space Mono',monospace;font-size:0.65rem;padding:0.3rem 0.8rem;
  border:1px solid var(--border);border-radius:999px;color:var(--muted)}}
.export-btn{{font-family:'Space Mono',monospace;font-size:0.65rem;padding:0.3rem 0.8rem;
  border:1px solid var(--accent);border-radius:999px;color:var(--accent);
  cursor:pointer;background:transparent;transition:all 0.2s}}
.export-btn:hover{{background:rgba(0,212,255,0.1)}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(270px,1fr));gap:0.85rem;margin-bottom:2.5rem;}}
.r-card{{background:var(--surface);border:1px solid var(--border);border-radius:1rem;padding:1.4rem;
  transition:border-color 0.2s,transform 0.15s;}}
.r-card:hover{{border-color:var(--accent);transform:translateY(-2px)}}
.r-label{{font-family:'Space Mono',monospace;font-size:0.65rem;color:var(--muted);
  letter-spacing:0.12em;text-transform:uppercase;display:block;margin-bottom:0.5rem}}
.r-val{{font-size:1.9rem;font-weight:800;font-family:'Space Mono',monospace;display:block;margin-bottom:0.65rem}}
.r-val.na{{color:var(--muted);font-size:1.4rem}}
.r-unit{{font-size:0.85rem;color:var(--muted);font-weight:400}}
.r-bar-bg{{height:3px;background:var(--border);border-radius:999px;margin-bottom:0.5rem}}
.r-bar{{height:3px;border-radius:999px}}
.r-who{{font-family:'Space Mono',monospace;font-size:0.6rem;color:var(--muted)}}
.section-title{{font-size:1rem;font-weight:700;color:var(--muted);letter-spacing:0.08em;
  text-transform:uppercase;margin-bottom:1rem;font-family:'Space Mono',monospace}}
.map-container{{background:var(--surface);border:1px solid var(--border);border-radius:1.5rem;
  overflow:hidden;height:300px;margin-bottom:2rem;}}
.chart-container{{background:var(--surface);border:1px solid var(--border);border-radius:1.5rem;
  padding:1.5rem;margin-bottom:2rem;}}
.search-row{{display:flex;gap:0;background:var(--surface);border:1px solid var(--border);
  border-radius:0.85rem;overflow:hidden;margin-bottom:3rem;transition:border-color 0.2s;}}
.search-row:focus-within{{border-color:var(--accent)}}
.s-input{{flex:1;background:transparent;border:none;outline:none;padding:1rem 1.25rem;
  color:var(--text);font-family:'Syne',sans-serif;font-size:1rem;}}
.s-input::placeholder{{color:var(--muted)}}
.s-btn{{background:var(--accent);color:#060b18;border:none;padding:1rem 1.75rem;
  font-family:'Syne',sans-serif;font-weight:700;font-size:0.9rem;cursor:pointer;
  transition:opacity 0.2s;white-space:nowrap;}}
.s-btn:hover{{opacity:0.85}}
footer{{border-top:1px solid var(--border);padding:1.5rem 2rem;text-align:center;
  max-width:1100px;margin:0 auto;}}
.fbadge{{display:inline-flex;align-items:center;gap:0.5rem;font-family:'Space Mono',monospace;
  font-size:0.65rem;color:var(--muted);text-decoration:none;border:1px solid var(--border);
  padding:0.4rem 1rem;border-radius:999px;transition:all 0.2s;}}
.fbadge:hover{{border-color:var(--accent);color:var(--accent)}}
.dot{{width:6px;height:6px;background:#00E676;border-radius:50%;animation:pulse 2s infinite}}
@keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:0.3}}}}
@media(max-width:640px){{
  .hri-block{{grid-template-columns:1fr;gap:1.5rem}}
  .score{{font-size:4rem}}
}}
</style>
</head>
<body>
<header>
  <span class="logo">BXP NODE</span>
  <nav>
    <a href="/dashboard">🔍 Search</a>
    <a href="/map">🗺 Map</a>
    <a href="/compare">⚖ Compare</a>
    <a href="/bxp/v2/city/{query}">JSON</a>
    <a href="/bxp/v2/health">Status</a>
    <a href="https://github.com/bxpprotocol/bxp-spec" target="_blank">GitHub</a>
  </nav>
</header>

<div class="main">
  <div class="loc">{location}</div>
  <div class="ts-row">
    <span class="ts" id="ts-label">Updated {timestamp[:19].replace("T"," ")} UTC · BXP v{BXP_VERSION} · {data.get("attribution","AQICN")}</span>
    <span class="refresh-badge" onclick="autoRefresh()" id="refresh-btn">⟳ Auto-refresh: OFF</span>
  </div>

  <div class="hri-block">
    <div class="score" id="hri-score">{hri}</div>
    <div>
      <div class="level" id="hri-level">{level}</div>
      <div class="advice" id="hri-advice">{advice}</div>
      <div class="pills">
        <span class="meta-pill">AQI {aqi}</span>
        {dominant_pill}
        <span class="meta-pill">BXP_HRI {hri}/100</span>
        <button class="export-btn" onclick="exportData()">↓ Export .bxp.json</button>
      </div>
    </div>
  </div>

  <div class="grid" id="readings-grid">{cards}</div>

  <div class="section-title">Location on Map</div>
  <div class="map-container" id="city-map"></div>

  <div class="section-title">HRI Scale Reference</div>
  <div class="chart-container">
    <canvas id="hriChart" height="80"></canvas>
  </div>

  <div class="search-row">
    <input class="s-input" id="si" placeholder="Search any city, town, or location worldwide..."
           onkeydown="if(event.key==='Enter')go()">
    <button class="s-btn" onclick="go()">Check Air →</button>
  </div>
</div>

<footer>
  <a href="https://github.com/bxpprotocol/bxp-spec" target="_blank" class="fbadge">
    <span class="dot"></span>
    BXP Protocol — Open Standard for Atmospheric Exposure Data · Apache 2.0
  </a>
</footer>

<script>
const CURRENT_DATA = {export_json};
const CITY_QUERY   = "{query}";
const CITY_LAT     = {data["location"].get("latitude") or "null"};
const CITY_LON     = {data["location"].get("longitude") or "null"};

// ── Map ─────────────────────────────────────────────────────
if (CITY_LAT && CITY_LON) {{
  const map = L.map('city-map', {{
    center: [CITY_LAT, CITY_LON],
    zoom: 10,
    zoomControl: true,
    attributionControl: true,
  }});
  L.tileLayer('https://{{s}}.basemaps.cartocdn.com/dark_all/{{z}}/{{x}}/{{y}}{{r}}.png', {{
    attribution: '© OpenStreetMap contributors © CARTO',
    subdomains: 'abcd', maxZoom: 19
  }}).addTo(map);
  const hri = CURRENT_DATA.bxp_hri.score;
  const color = CURRENT_DATA.bxp_hri.color;
  L.circleMarker([CITY_LAT, CITY_LON], {{
    radius: 16, fillColor: color, color: color,
    weight: 2, opacity: 0.9, fillOpacity: 0.4,
  }}).bindPopup(`<b>${{CURRENT_DATA.location.name}}</b><br>HRI: ${{hri}} ${{CURRENT_DATA.bxp_hri.level}}`)
    .addTo(map).openPopup();
}} else {{
  document.getElementById('city-map').innerHTML =
    '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#4a5568">No coordinates available for map</div>';
}}

// ── HRI scale chart ─────────────────────────────────────────
const ctx = document.getElementById('hriChart').getContext('2d');
new Chart(ctx, {{
  type: 'bar',
  data: {{
    labels: ['CLEAN', 'MODERATE', 'ELEVATED', 'HIGH', 'VERY HIGH', 'HAZARDOUS'],
    datasets: [{{
      data: [20, 20, 20, 15, 15, 10],
      backgroundColor: ['#00E676','#FFEB3B','#FF9800','#F44336','#9C27B0','#4A0000'],
      borderWidth: 0,
      borderRadius: 4,
    }}]
  }},
  options: {{
    indexAxis: 'y',
    responsive: true,
    plugins: {{
      legend: {{ display: false }},
      tooltip: {{ enabled: false }},
      annotation: {{}}
    }},
    scales: {{
      x: {{
        stacked: true,
        display: false,
        max: 100,
      }},
      y: {{
        ticks: {{
          color: '#4a5568',
          font: {{ family: "'Space Mono', monospace", size: 11 }}
        }},
        grid: {{ display: false }},
        border: {{ display: false }},
      }}
    }},
  }}
}});

// ── Auto-refresh ────────────────────────────────────────────
let refreshTimer = null;
function autoRefresh() {{
  if (refreshTimer) {{
    clearInterval(refreshTimer);
    refreshTimer = null;
    document.getElementById('refresh-btn').textContent = '⟳ Auto-refresh: OFF';
  }} else {{
    refreshTimer = setInterval(refreshCityData, 60000);
    document.getElementById('refresh-btn').textContent = '⟳ Auto-refresh: ON (60s)';
  }}
}}

async function refreshCityData() {{
  try {{
    const r = await fetch('/bxp/v2/city/' + encodeURIComponent(CITY_QUERY));
    if (!r.ok) return;
    const d = await r.json();
    document.getElementById('hri-score').textContent = d.bxp_hri.score;
    document.getElementById('hri-level').textContent = d.bxp_hri.level;
    document.getElementById('hri-advice').textContent = d.bxp_hri.advice;
    document.getElementById('ts-label').textContent =
      'Updated ' + d.timestamp.slice(0,19).replace('T',' ') + ' UTC · auto-refreshed';
  }} catch(e) {{}}
}}

// ── Export ──────────────────────────────────────────────────
function exportData() {{
  const blob = new Blob([JSON.stringify(CURRENT_DATA, null, 2)],
    {{type: 'application/json'}});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = CITY_QUERY.replace(/\\s+/g, '_') + '.bxp.json';
  a.click();
}}

// ── Search ───────────────────────────────────────────────────
function go() {{
  const v = document.getElementById('si').value.trim();
  if (v) window.location.href = '/dashboard/' + encodeURIComponent(v);
}}
</script>
</body>
</html>"""


# ─── Map page ─────────────────────────────────────────────────

MAP_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>BXP — Global Air Quality Map</title>
<link href="https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Syne:wght@400;700;800&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{--bg:#060b18;--surface:#0d1628;--border:#1a2540;--text:#e8edf5;--muted:#4a5568;--accent:#00d4ff}
body{background:var(--bg);color:var(--text);font-family:'Syne',sans-serif;height:100vh;display:flex;flex-direction:column;}
header{padding:1rem 2rem;display:flex;align-items:center;justify-content:space-between;
  border-bottom:1px solid var(--border);background:rgba(6,11,24,0.95);z-index:1000;flex-shrink:0;}
.logo{font-family:'Space Mono',monospace;font-size:0.9rem;color:var(--accent);letter-spacing:0.15em}
nav a{color:var(--muted);text-decoration:none;margin-left:1.5rem;font-size:0.82rem;transition:color 0.2s}
nav a:hover{color:var(--accent)}
#map{flex:1}
.map-legend{position:absolute;bottom:2rem;right:1rem;z-index:1000;
  background:rgba(6,11,24,0.9);border:1px solid var(--border);
  border-radius:1rem;padding:1rem;font-family:'Space Mono',monospace;font-size:0.65rem;}
.legend-row{display:flex;align-items:center;gap:0.5rem;margin-bottom:0.4rem;color:var(--muted)}
.legend-dot{width:12px;height:12px;border-radius:50%;flex-shrink:0}
.map-status{position:absolute;top:5rem;left:1rem;z-index:1000;
  background:rgba(6,11,24,0.9);border:1px solid var(--border);
  border-radius:0.75rem;padding:0.75rem 1rem;font-family:'Space Mono',monospace;font-size:0.7rem;color:var(--muted)}
</style>
</head>
<body>
<header>
  <span class="logo">BXP GLOBAL MAP</span>
  <nav>
    <a href="/dashboard">🔍 Search</a>
    <a href="/compare">⚖ Compare</a>
    <a href="/">Home</a>
  </nav>
</header>
<div id="map"></div>
<div class="map-status" id="map-status">Loading city data…</div>
<div class="map-legend">
  <div class="legend-row"><div class="legend-dot" style="background:#00E676"></div> CLEAN (0–20)</div>
  <div class="legend-row"><div class="legend-dot" style="background:#FFEB3B"></div> MODERATE (21–40)</div>
  <div class="legend-row"><div class="legend-dot" style="background:#FF9800"></div> ELEVATED (41–60)</div>
  <div class="legend-row"><div class="legend-dot" style="background:#F44336"></div> HIGH (61–75)</div>
  <div class="legend-row"><div class="legend-dot" style="background:#9C27B0"></div> VERY HIGH (76–90)</div>
  <div class="legend-row"><div class="legend-dot" style="background:#4A0000"></div> HAZARDOUS (91+)</div>
</div>
<script>
const map = L.map('map', {
  center: [20, 10], zoom: 2,
  zoomControl: true,
});
L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
  attribution: '© OpenStreetMap contributors © CARTO',
  subdomains: 'abcd', maxZoom: 19
}).addTo(map);

async function loadCities() {
  try {
    const r = await fetch('/bxp/v2/readings');
    const d = await r.json();
    const readings = d.data?.readings || [];
    let loaded = 0;
    for (const rec of readings) {
      const lat = rec.location?.latitude;
      const lon = rec.location?.longitude;
      if (!lat || !lon) continue;
      const hri   = rec.bxp_hri?.score ?? 0;
      const level = rec.bxp_hri?.level ?? '';
      const color = rec.bxp_hri?.color ?? '#4a5568';
      const name  = rec.location?.name ?? 'Unknown';
      L.circleMarker([lat, lon], {
        radius: 14 + Math.min(hri / 10, 8),
        fillColor: color, color: color,
        weight: 2, opacity: 0.9, fillOpacity: 0.45,
      }).bindPopup(
        `<b>${name}</b><br>HRI: ${hri} <b style="color:${color}">${level}</b>` +
        `<br><a href="/dashboard/${encodeURIComponent(rec.location?.query ?? name)}" ` +
        `style="color:#00d4ff">View dashboard →</a>`
      ).addTo(map);
      loaded++;
    }
    document.getElementById('map-status').textContent =
      loaded + ' locations loaded';
    setTimeout(() => document.getElementById('map-status').style.display='none', 3000);
  } catch(e) {
    document.getElementById('map-status').textContent = 'Error loading data';
  }
}
loadCities();
</script>
</body>
</html>"""


# ─── Compare page ─────────────────────────────────────────────

COMPARE_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>BXP — Compare Cities</title>
<link href="https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Syne:wght@400;700;800&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{--bg:#060b18;--surface:#0d1628;--border:#1a2540;--text:#e8edf5;--muted:#4a5568;--accent:#00d4ff}
body{background:var(--bg);color:var(--text);font-family:'Syne',sans-serif;min-height:100vh;}
header{padding:1.25rem 2rem;display:flex;align-items:center;justify-content:space-between;
  border-bottom:1px solid var(--border);background:rgba(6,11,24,0.92);
  backdrop-filter:blur(12px);position:sticky;top:0;z-index:100;}
.logo{font-family:'Space Mono',monospace;font-size:0.9rem;color:var(--accent);letter-spacing:0.15em}
nav a{color:var(--muted);text-decoration:none;margin-left:1.5rem;font-size:0.82rem;transition:color 0.2s}
nav a:hover{color:var(--accent)}
.main{max-width:1200px;margin:0 auto;padding:3rem 2rem}
h1{font-size:2.5rem;font-weight:800;margin-bottom:0.5rem}
.sub{color:var(--muted);margin-bottom:2.5rem}
.add-row{display:flex;gap:0;background:var(--surface);border:1px solid var(--border);
  border-radius:0.85rem;overflow:hidden;margin-bottom:2rem;transition:border-color 0.2s;max-width:500px}
.add-row:focus-within{border-color:var(--accent)}
.a-input{flex:1;background:transparent;border:none;outline:none;padding:0.85rem 1.25rem;
  color:var(--text);font-family:'Syne',sans-serif;font-size:0.95rem;}
.a-input::placeholder{color:var(--muted)}
.a-btn{background:var(--accent);color:#060b18;border:none;padding:0.85rem 1.5rem;
  font-family:'Syne',sans-serif;font-weight:700;font-size:0.85rem;cursor:pointer;white-space:nowrap;}
.a-btn:hover{opacity:0.85}
.chips{display:flex;flex-wrap:wrap;gap:0.5rem;margin-bottom:2rem}
.chip{font-family:'Space Mono',monospace;font-size:0.65rem;padding:0.35rem 0.9rem;
  border:1px solid var(--border);border-radius:999px;color:var(--muted);
  cursor:pointer;background:var(--surface);display:flex;align-items:center;gap:0.5rem;
  transition:all 0.2s}
.chip:hover{border-color:#F44336;color:#F44336}
.chart-wrap{background:var(--surface);border:1px solid var(--border);border-radius:1.5rem;
  padding:2rem;margin-bottom:2rem}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:1rem;margin-bottom:2rem}
.ccard{background:var(--surface);border:1px solid var(--border);border-radius:1rem;padding:1.5rem;
  position:relative;overflow:hidden;transition:transform 0.15s}
.ccard:hover{transform:translateY(-2px)}
.cc-name{font-size:0.8rem;color:var(--muted);margin-bottom:0.5rem;font-weight:700}
.cc-hri{font-size:3rem;font-weight:800;font-family:'Space Mono',monospace;line-height:1}
.cc-level{font-size:0.75rem;font-weight:700;letter-spacing:0.08em;margin-top:0.25rem}
.cc-bar{position:absolute;bottom:0;left:0;height:3px}
.loading{color:var(--muted);font-style:italic;font-size:0.85rem}
</style>
</head>
<body>
<header>
  <span class="logo">BXP COMPARE</span>
  <nav>
    <a href="/dashboard">🔍 Search</a>
    <a href="/map">🗺 Map</a>
    <a href="/">Home</a>
  </nav>
</header>

<div class="main">
  <h1>Compare Cities</h1>
  <p class="sub">Add up to 10 cities to compare air quality side-by-side.</p>

  <div class="add-row">
    <input class="a-input" id="city-input" placeholder="Add a city…"
           onkeydown="if(event.key==='Enter')addCity()">
    <button class="a-btn" onclick="addCity()">Add</button>
  </div>

  <div class="chips" id="chips"></div>

  <div class="chart-wrap" id="chart-wrap" style="display:none">
    <canvas id="compareChart"></canvas>
  </div>

  <div class="cards" id="city-cards"></div>
</div>

<script>
const cities = new Map();
let chart = null;

const DEFAULTS = ['accra','delhi','london','new york','beijing'];
DEFAULTS.forEach(c => loadCity(c));

async function loadCity(name) {
  if (cities.size >= 10) { alert('Maximum 10 cities'); return; }
  const key = name.toLowerCase().trim();
  if (cities.has(key)) return;
  cities.set(key, {name: key, loading: true});
  renderAll();
  try {
    const r = await fetch('/bxp/v2/city/' + encodeURIComponent(key));
    if (!r.ok) { cities.delete(key); renderAll(); return; }
    const d = await r.json();
    cities.set(key, {
      name: d.location?.name ?? key,
      query: key,
      hri:   d.bxp_hri?.score ?? 0,
      level: d.bxp_hri?.level ?? '',
      color: d.bxp_hri?.color ?? '#4a5568',
    });
  } catch(e) {
    cities.delete(key);
  }
  renderAll();
}

function addCity() {
  const v = document.getElementById('city-input').value.trim();
  if (!v) return;
  document.getElementById('city-input').value = '';
  loadCity(v);
}

function removeCity(key) {
  cities.delete(key);
  renderAll();
}

function renderAll() {
  const data = [...cities.values()].filter(c => !c.loading);

  // Chips
  document.getElementById('chips').innerHTML = [...cities.entries()].map(([k, c]) =>
    `<div class="chip" onclick="removeCity('${k}')">
      ${c.name ?? k} ${c.loading ? '…' : '✕'}
    </div>`
  ).join('');

  // Cards
  document.getElementById('city-cards').innerHTML = data.map(c =>
    `<div class="ccard">
      <div class="cc-name">${c.name}</div>
      <div class="cc-hri" style="color:${c.color}">${c.hri}</div>
      <div class="cc-level" style="color:${c.color}">${c.level}</div>
      <div class="cc-bar" style="background:${c.color};width:${c.hri}%"></div>
    </div>`
  ).join('');

  // Chart
  if (data.length === 0) {
    document.getElementById('chart-wrap').style.display = 'none';
    if (chart) { chart.destroy(); chart = null; }
    return;
  }
  document.getElementById('chart-wrap').style.display = 'block';
  const labels = data.map(c => c.name);
  const values = data.map(c => c.hri);
  const colors = data.map(c => c.color);

  if (chart) chart.destroy();
  const ctx = document.getElementById('compareChart').getContext('2d');
  chart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        data: values,
        backgroundColor: colors.map(c => c + '80'),
        borderColor: colors,
        borderWidth: 2,
        borderRadius: 6,
      }]
    },
    options: {
      responsive: true,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: ctx => `HRI: ${ctx.raw}`,
          }
        }
      },
      scales: {
        y: {
          min: 0, max: 100,
          ticks: { color: '#4a5568', font: { family: "'Space Mono', monospace" } },
          grid: { color: '#1a2540' },
          border: { display: false },
        },
        x: {
          ticks: { color: '#94a3b8', font: { family: "'Syne', sans-serif", weight: '700' } },
          grid: { display: false },
          border: { display: false },
        }
      }
    }
  });
}
</script>
</body>
</html>"""


# ─── Search page ──────────────────────────────────────────────

SEARCH_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>BXP — Global Air Quality</title>
<link href="https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Syne:wght@400;700;800&display=swap" rel="stylesheet">
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#060b18;color:#e8edf5;font-family:'Syne',sans-serif;min-height:100vh;
  display:flex;flex-direction:column;align-items:center;justify-content:center;
  background-image:radial-gradient(ellipse at 50% 40%,rgba(0,212,255,0.05) 0%,transparent 65%);}
.title{font-size:clamp(2.5rem,7vw,5.5rem);font-weight:800;text-align:center;
  letter-spacing:-0.03em;line-height:0.95;margin-bottom:1.25rem;}
.title span{color:#00d4ff}
.sub{color:#4a5568;text-align:center;margin-bottom:3rem;font-size:1rem;max-width:420px;line-height:1.7}
.wrap{width:100%;max-width:580px;padding:0 1.5rem}
.box{display:flex;background:#0d1628;border:1px solid #1a2540;border-radius:1rem;
  overflow:hidden;transition:border-color 0.2s;}
.box:focus-within{border-color:#00d4ff}
input{flex:1;background:transparent;border:none;outline:none;padding:1.2rem 1.5rem;
  color:#e8edf5;font-family:'Syne',sans-serif;font-size:1.05rem;}
input::placeholder{color:#2d3748}
button{background:#00d4ff;color:#060b18;border:none;padding:1.2rem 2rem;
  font-family:'Syne',sans-serif;font-weight:700;font-size:0.95rem;cursor:pointer;
  transition:background 0.2s;white-space:nowrap;}
button:hover{background:#00b8d9}
.cities{display:flex;flex-wrap:wrap;gap:0.5rem;justify-content:center;
  margin-top:2rem;max-width:580px;padding:0 1.5rem;}
.cp{font-family:'Space Mono',monospace;font-size:0.65rem;padding:0.35rem 0.9rem;
  border:1px solid #1a2540;border-radius:999px;color:#4a5568;cursor:pointer;
  transition:all 0.2s;text-decoration:none;}
.cp:hover{border-color:#00d4ff;color:#00d4ff}
.nav-links{display:flex;gap:1.5rem;margin-top:2.5rem;}
.nav-link{font-family:'Space Mono',monospace;font-size:0.7rem;color:#4a5568;
  text-decoration:none;transition:color 0.2s;}
.nav-link:hover{color:#00d4ff}
.foot{position:fixed;bottom:1.5rem;font-family:'Space Mono',monospace;font-size:0.6rem;color:#2d3748;}
.foot a{color:#2d3748;text-decoration:none;transition:color 0.2s}
.foot a:hover{color:#00d4ff}
</style>
</head>
<body>
<div class="title">Air quality<br>for <span>every place</span><br>on earth.</div>
<div class="sub">Real-time atmospheric exposure data. Powered by BXP — the open standard.</div>
<div class="wrap">
  <div class="box">
    <input id="ci" placeholder="Any city, town, village, or location…" autofocus
           onkeydown="if(event.key==='Enter')go()">
    <button onclick="go()">Check Air →</button>
  </div>
</div>
<div class="cities">
  <a class="cp" href="/dashboard/accra">Accra</a>
  <a class="cp" href="/dashboard/lagos">Lagos</a>
  <a class="cp" href="/dashboard/nairobi">Nairobi</a>
  <a class="cp" href="/dashboard/cairo">Cairo</a>
  <a class="cp" href="/dashboard/casablanca">Casablanca</a>
  <a class="cp" href="/dashboard/johannesburg">Johannesburg</a>
  <a class="cp" href="/dashboard/delhi">Delhi</a>
  <a class="cp" href="/dashboard/beijing">Beijing</a>
  <a class="cp" href="/dashboard/jakarta">Jakarta</a>
  <a class="cp" href="/dashboard/tokyo">Tokyo</a>
  <a class="cp" href="/dashboard/mumbai">Mumbai</a>
  <a class="cp" href="/dashboard/dhaka">Dhaka</a>
  <a class="cp" href="/dashboard/karachi">Karachi</a>
  <a class="cp" href="/dashboard/seoul">Seoul</a>
  <a class="cp" href="/dashboard/london">London</a>
  <a class="cp" href="/dashboard/paris">Paris</a>
  <a class="cp" href="/dashboard/berlin">Berlin</a>
  <a class="cp" href="/dashboard/new york">New York</a>
  <a class="cp" href="/dashboard/los angeles">Los Angeles</a>
  <a class="cp" href="/dashboard/sao paulo">São Paulo</a>
  <a class="cp" href="/dashboard/mexico city">Mexico City</a>
  <a class="cp" href="/dashboard/buenos aires">Buenos Aires</a>
  <a class="cp" href="/dashboard/sydney">Sydney</a>
  <a class="cp" href="/dashboard/toronto">Toronto</a>
</div>
<div class="nav-links">
  <a class="nav-link" href="/map">🗺 Global Map</a>
  <a class="nav-link" href="/compare">⚖ Compare Cities</a>
  <a class="nav-link" href="/docs">API Docs</a>
  <a class="nav-link" href="/metrics">Metrics</a>
</div>
<div class="foot">
  <a href="/">BXP Protocol</a> ·
  <a href="/bxp/v2/health">Node Status</a> ·
  <a href="/docs">API</a> ·
  <a href="https://github.com/bxpprotocol/bxp-spec" target="_blank">GitHub</a>
</div>
<script>
function go(){
  const v=document.getElementById('ci').value.trim();
  if(v) window.location.href='/dashboard/'+encodeURIComponent(v);
}
</script>
</body>
</html>"""


# ─── Landing page ─────────────────────────────────────────────

LANDING_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>BXP Protocol — Open Standard for Atmospheric Exposure Data</title>
<link href="https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Syne:wght@400;700;800&display=swap" rel="stylesheet">
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{--bg:#060b18;--surface:#0d1628;--border:#1a2540;--text:#e8edf5;--muted:#4a5568;--accent:#00d4ff}
body{background:var(--bg);color:var(--text);font-family:'Syne',sans-serif;
  background-image:radial-gradient(ellipse at 20% 20%,rgba(0,212,255,0.04) 0%,transparent 60%);}
header{padding:1.25rem 2rem;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid var(--border);}
.logo{font-family:'Space Mono',monospace;font-size:0.9rem;color:var(--accent);letter-spacing:0.15em}
nav a{color:var(--muted);text-decoration:none;margin-left:1.5rem;font-size:0.82rem;transition:color 0.2s}
nav a:hover{color:var(--accent)}
.hero{max-width:900px;margin:5rem auto;padding:0 2rem;text-align:center}
h1{font-size:clamp(2.8rem,7vw,5.5rem);font-weight:800;letter-spacing:-0.03em;line-height:0.95;margin-bottom:1.25rem}
h1 span{color:var(--accent)}
.tag{font-size:1.1rem;color:#94a3b8;max-width:520px;margin:0 auto 2.5rem;line-height:1.7}
.ctas{display:flex;gap:1rem;justify-content:center;flex-wrap:wrap;margin-bottom:5rem}
.btn-p{background:var(--accent);color:#060b18;padding:0.9rem 2.25rem;border-radius:0.75rem;
  font-family:'Syne',sans-serif;font-weight:700;font-size:0.95rem;text-decoration:none;transition:opacity 0.2s}
.btn-p:hover{opacity:0.85}
.btn-s{background:transparent;color:var(--text);padding:0.9rem 2.25rem;border-radius:0.75rem;
  font-family:'Syne',sans-serif;font-weight:700;font-size:0.95rem;text-decoration:none;
  border:1px solid var(--border);transition:border-color 0.2s}
.btn-s:hover{border-color:var(--accent)}
.stats{display:flex;justify-content:center;gap:4rem;flex-wrap:wrap;padding:2.5rem;
  background:var(--surface);border:1px solid var(--border);border-radius:1.5rem;
  max-width:750px;margin:0 auto 5rem;}
.sv{font-size:2.5rem;font-weight:800;font-family:'Space Mono',monospace;color:var(--accent);display:block}
.sl{font-size:0.72rem;color:var(--muted);text-transform:uppercase;letter-spacing:0.1em;margin-top:0.2rem}
.code{background:var(--surface);border:1px solid var(--border);border-radius:1rem;
  padding:1.5rem 2rem;font-family:'Space Mono',monospace;font-size:0.82rem;
  text-align:left;max-width:560px;margin:0 auto 5rem;line-height:2.1;color:#94a3b8;}
.cm{color:var(--muted)}.cd{color:var(--accent)}
.sec{max-width:900px;margin:0 auto 5rem;padding:0 2rem}
.st{font-size:1.8rem;font-weight:800;margin-bottom:1.75rem;letter-spacing:-0.02em}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:1rem}
.card{background:var(--surface);border:1px solid var(--border);border-radius:1rem;padding:1.5rem}
.ci{font-size:1.4rem;margin-bottom:0.65rem}
.ct{font-weight:700;margin-bottom:0.4rem}
.cb{color:#94a3b8;font-size:0.88rem;line-height:1.6}
footer{border-top:1px solid var(--border);padding:2rem;text-align:center;
  font-family:'Space Mono',monospace;font-size:0.65rem;color:var(--muted);}
footer a{color:var(--muted);text-decoration:none;transition:color 0.2s}
footer a:hover{color:var(--accent)}
.dot{width:7px;height:7px;background:#00E676;border-radius:50%;
  display:inline-block;animation:p 2s infinite;margin-right:0.4rem;vertical-align:middle}
@keyframes p{0%,100%{opacity:1}50%{opacity:0.3}}
</style>
</head>
<body>
<header>
  <span class="logo">BXP PROTOCOL</span>
  <nav>
    <a href="/dashboard">Dashboard</a>
    <a href="/map">Map</a>
    <a href="/compare">Compare</a>
    <a href="/bxp/v2/health">Status</a>
    <a href="/docs">API</a>
    <a href="https://github.com/bxpprotocol/bxp-spec" target="_blank">GitHub</a>
  </nav>
</header>

<div class="hero">
  <h1>The open standard<br>for <span>air quality</span><br>data.</h1>
  <p class="tag">Like HTTP for the web — any device writes it, any software reads it, nobody owns it. Apache 2.0. Forever free.</p>
  <div class="ctas">
    <a href="/dashboard" class="btn-p">Live Global Dashboard →</a>
    <a href="https://github.com/bxpprotocol/bxp-spec" target="_blank" class="btn-s">View Specification</a>
  </div>
  <div class="stats">
    <div><span class="sv">7M</span><span class="sl">Deaths per year</span></div>
    <div><span class="sv">31</span><span class="sl">Atmospheric agents</span></div>
    <div><span class="sv">∞</span><span class="sl">Cities worldwide</span></div>
  </div>
  <div class="code">
    <span class="cm"># Run your own BXP node in 3 minutes</span><br>
    <span class="cd">git clone</span> https://github.com/bxpprotocol/bxp-spec<br>
    <span class="cd">cd</span> bxp-spec/reference-server<br>
    <span class="cd">pip install</span> -r requirements.txt<br>
    <span class="cd">python</span> server.py
  </div>
</div>

<div class="sec">
  <div class="st">What BXP defines</div>
  <div class="grid">
    <div class="card"><div class="ci">📄</div><div class="ct">Universal File Format</div>
      <div class="cb">A .bxp file any device or software can read and write. One format. Every sensor. Everywhere.</div></div>
    <div class="card"><div class="ci">📊</div><div class="ct">BXP_HRI Score</div>
      <div class="cb">Composite Health Risk Index with WHO-derived weighting across all atmospheric agents. 0–100.</div></div>
    <div class="card"><div class="ci">🌐</div><div class="ct">REST API Spec</div>
      <div class="cb">Federated node architecture. Any institution runs a node. Nodes interoperate. Nobody owns the network.</div></div>
    <div class="card"><div class="ci">🔒</div><div class="ct">Privacy Framework</div>
      <div class="cb">Individual records protected by design. Geohash-5 floor. k≥5 anonymity. Cryptographic deletion.</div></div>
    <div class="card"><div class="ci">🗺</div><div class="ct">Global Map</div>
      <div class="cb">Real-time air quality plotted worldwide. Click any marker to see the full city dashboard.</div></div>
    <div class="card"><div class="ci">⚖</div><div class="ct">City Comparison</div>
      <div class="cb">Side-by-side HRI comparison for up to 10 cities. Ideal for researchers and health professionals.</div></div>
  </div>
</div>

<div class="sec" style="text-align:center">
  <div class="st">Live public node</div>
  <p style="color:#94a3b8;margin-bottom:2rem"><span class="dot"></span>Operational — real-time global data</p>
  <a href="/dashboard" class="btn-p">Open Global Dashboard →</a>
</div>

<footer>
  BXP Protocol · Apache 2.0 ·
  <a href="https://doi.org/10.5281/zenodo.18906812" target="_blank">DOI 10.5281/zenodo.18906812</a> ·
  <a href="https://github.com/bxpprotocol/bxp-spec" target="_blank">GitHub</a> ·
  <a href="mailto:bxpprotocol@proton.me">Contact</a>
</footer>
</body>
</html>"""


if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=5000, reload=False)
