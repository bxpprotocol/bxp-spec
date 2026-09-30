"""
BXP Protocol Reference Node v2.1

A small FastAPI node that stores BXP readings (JSON or native binary .bxp),
serves them back, ranks nearby observations, replicates to peers via /sync, and
optionally proxies live city data from AQICN. Persistence is SQLite
(database.py); spatial maths is geo.py; the health index is hri.py; HTML is
pages.py. Routes are grouped below by resource. Configuration is by
environment variable - see .env.example.
"""

import asyncio
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import sys
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional
from urllib.parse import quote, urlsplit

import httpx
import uvicorn
from fastapi import FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field
from pydantic import ValidationError as PydanticValidationError

# Binary .bxp container support (spec §5.1-5.2) — sibling SDK module.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "sdk" / "python"))
from bxp_binary import (
    encode_bxp_binary, decode_bxp_binary, BXPBinaryError,
)

import geo
import pages
from database import (
    init_db, insert_readings, get_reading, delete_reading, verify_reading,
    query_readings, get_geohash_latest, get_geohash_history, get_aggregate,
    reading_count, register_device, get_device, validate_token,
    is_registered_device, bump_device_seen, insert_report, query_reports,
    upsert_node, get_nodes, get_nearby_readings, get_readings_since,
    canonical_payload_hash, DeviceExistsError, NodeRegistryError, QUALITY_RANK,
)
from hri import (  # noqa: F401  (re-exported: tests and callers import these from `server`)
    AGENT_ID_MAP, BXP_VERSION, WHO_THRESHOLDS, WEIGHTS,
    calculate_hri, hri_level, hri_color, hri_advice, assess_quality,
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
NODE_ID      = os.environ.get("BXP_NODE_ID", "bxp-public-node-001")
# Shared-secret gate for GET /bxp/v2/sync (spec §7 Stage 7 / §8.2.2 calls
# for "Node Token" auth). Full node identity/trust/reputation is
# explicitly deferred to a future RFC per spec §7 — this env var is a
# functional placeholder for that, not the eventual trust system. If
# unset, /sync is open (consistent with this reference server's other
# not-yet-hardened auth columns, e.g. devices/register's unenforced
# "API Key").
BXP_NODE_SYNC_TOKEN = os.environ.get("BXP_NODE_SYNC_TOKEN", "")
NODE_TYPE    = os.environ.get("BXP_NODE_TYPE", "reference")


# Upper bounds on client-controlled sizes. Every list/string a client can send
# is capped so a single request cannot make the node do unbounded work.
MAX_BATCH_READINGS = 500
MAX_AGENTS_PER_READING = 64
MAX_READING_BYTES = 64 * 1024
MAX_TIMESTAMP_US = 4_102_444_800_000_000   # 2100-01-01 UTC
_ID_PATTERN = r"^[A-Za-z0-9._:\-]{1,64}$"


class AgentReading(BaseModel):
    # extra="allow": uncertainty, method, belowLod and the SPEC.md 5.5.1
    # `correction` object must survive ingestion (SPEC.md 5.7: ignore-and-preserve).
    model_config = ConfigDict(extra="allow")

    agentId: str = Field(min_length=1, max_length=32)
    # NaN/Infinity pass a naive `v < 0` check and would poison HRI maths and JSON.
    value:   float = Field(ge=0, allow_inf_nan=False)
    unit:    Optional[str] = Field(default=None, max_length=32)


class RawReading(BaseModel):
    model_config = ConfigDict(extra="allow")

    deviceUuid:   Optional[str] = Field(default=None, pattern=_ID_PATTERN)
    latitude:     float = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude:    float = Field(ge=-180, le=180, allow_inf_nan=False)
    timestampUs:  Optional[int] = Field(default=None, ge=0, le=MAX_TIMESTAMP_US)
    agents:       List[AgentReading] = Field(default_factory=list, max_length=MAX_AGENTS_PER_READING)
    durationS:    Optional[int] = Field(default=60, ge=0, le=366 * 86400)
    indoorOutdoor: Optional[str] = Field(default="outdoor", max_length=16)


class SubmitReadingsRequest(BaseModel):
    readings: List[RawReading] = Field(max_length=MAX_BATCH_READINGS)


class DeviceRegisterRequest(BaseModel):
    deviceUuid: Optional[str] = Field(default=None, pattern=_ID_PATTERN)
    label:      Optional[str] = Field(default=None, max_length=128)
    ownerHash:  Optional[str] = Field(default=None, max_length=128)  # pre-hashed owner ID (SPEC.md 9)


class CommunityReportRequest(BaseModel):
    latitude:    float = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude:   float = Field(ge=-180, le=180, allow_inf_nan=False)
    reportType:  str = Field(default="observation", max_length=64)
    description: Optional[str] = Field(default=None, max_length=2000)
    severity:    Optional[str] = Field(default=None, max_length=32)
    submitterHash: Optional[str] = Field(default=None, max_length=128)  # SHA-256 of person ID (SPEC.md 9)


# ─── Rate limiter ─────────────────────────────────────────────

class RateLimiter:
    """Sliding-window rate limiter — in-memory per-key (normally per-IP).

    Stale keys are swept out periodically. Without this, every distinct
    key ever seen stays in the dict forever, so a client that can vary
    its apparent IP (see _client_ip) grows server memory without bound
    even while never tripping the limit.
    """
    _SWEEP_EVERY = 1000  # checks between full sweeps of expired keys

    def __init__(self, calls: int, window_s: int):
        self._calls  = calls
        self._window = window_s
        self._store: dict[str, list] = {}
        self._lock = asyncio.Lock()
        self._since_sweep = 0

    def _sweep(self, window_start: float) -> None:
        stale = [k for k, hist in self._store.items()
                 if not hist or hist[-1] <= window_start]
        for k in stale:
            del self._store[k]

    async def check(self, key: str) -> bool:
        async with self._lock:
            now = time.time()
            window_start = now - self._window

            self._since_sweep += 1
            if self._since_sweep >= self._SWEEP_EVERY:
                self._sweep(window_start)
                self._since_sweep = 0

            hist = [t for t in self._store.get(key, []) if t > window_start]
            if len(hist) >= self._calls:
                self._store[key] = hist
                return False
            hist.append(now)
            self._store[key] = hist
            return True

    def reset(self):
        """Clear all rate-limit state (useful in tests)."""
        self._store.clear()
        self._since_sweep = 0


_rl_submit   = RateLimiter(30,  60)   # 30 submissions / minute
_rl_city     = RateLimiter(60,  60)   # 60 city lookups / minute
_rl_register = RateLimiter(5,   60)   # 5 device registrations / minute


# Hard cap on request body size. Requests are otherwise read fully into
# memory, so without this any client can exhaust it with one large upload.
MAX_BODY_BYTES = int(os.environ.get("BXP_MAX_BODY_BYTES") or 8 * 1024 * 1024)


async def _read_body_capped(request: Request) -> bytes:
    """Read the request body, aborting with 413 once it exceeds MAX_BODY_BYTES.

    Counts bytes as they stream in, so it also stops chunked uploads that
    carry no Content-Length header.
    """
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_BODY_BYTES:
        raise HTTPException(status_code=413, detail="Request body too large.")
    chunks, total = [], 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > MAX_BODY_BYTES:
            raise HTTPException(status_code=413, detail="Request body too large.")
        chunks.append(chunk)
    return b"".join(chunks)


# X-Forwarded-For is only trustworthy when the server sits behind a
# reverse proxy that overwrites it. If BXP is exposed directly, any client
# can send an arbitrary value and dodge every per-IP rate limit. So it is
# ignored unless the operator explicitly opts in.
TRUST_PROXY_HEADERS = os.environ.get("BXP_TRUST_PROXY_HEADERS", "").lower() in (
    "1", "true", "yes",
)


def _client_ip(request: Request) -> str:
    if TRUST_PROXY_HEADERS:
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# ─── Binary .bxp container helpers (spec §5.1-5.2) ────────────

def _binary_response(record: dict, file_type: str = "reading", compress: bool = False) -> Response:
    """Wrap a dict as a binary .bxp container and return it as an HTTP response."""
    raw = encode_bxp_binary(record, file_type=file_type, compress=compress)
    return Response(
        content=raw,
        media_type="application/octet-stream",
        headers={"X-BXP-Format": "binary"},
    )


def _is_binary_bxp_body(raw: bytes) -> bool:
    """Detect a binary .bxp container by its magic number (0x42585000, 'BXP\\0')."""
    return len(raw) >= 4 and raw[:4] == b"\x42\x58\x50\x00"


async def _parse_submit_body(request: Request) -> "SubmitReadingsRequest":
    """
    Parse a POST /bxp/v2/readings body as either JSON (spec §2 REST API) or
    a binary `.bxp` container (spec §5.1/5.2), auto-detected by magic number
    rather than trusting Content-Type — devices don't always set it right.

    A binary body may be either a single reading record (as write_bxp_binary
    produces) or a container-shaped dict with a "readings" list; both are
    normalized into a SubmitReadingsRequest.
    """
    raw = await _read_body_capped(request)

    if _is_binary_bxp_body(raw):
        try:
            decoded = decode_bxp_binary(raw)
        except BXPBinaryError as e:
            raise HTTPException(status_code=400, detail=f"Invalid binary .bxp container: {e}")
        record = decoded["record"]
        readings = record["readings"] if isinstance(record.get("readings"), list) else [record]
        try:
            return SubmitReadingsRequest.model_validate({"readings": readings})
        except PydanticValidationError as e:
            raise HTTPException(status_code=422, detail=json.loads(e.json()))

    try:
        payload = json.loads(raw.decode("utf-8"), parse_constant=lambda _: (_ for _ in ()).throw(ValueError("NaN/Infinity not allowed")))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as e:
        raise HTTPException(status_code=400, detail=f"Body is neither valid JSON nor a binary .bxp container: {e}")
    # 422, not 400, to match FastAPI's normal request-validation status code
    # for a well-formed-but-invalid JSON body (spec-level field errors).
    try:
        return SubmitReadingsRequest.model_validate(payload)
    except PydanticValidationError as e:
        error_detail = json.loads(e.json())
        def sanitize(obj):
            if isinstance(obj, float):
                if obj != obj or obj == float('inf') or obj == float('-inf'):
                    return str(obj)
                return obj
            if isinstance(obj, dict):
                return {k: sanitize(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [sanitize(v) for v in obj]
            return obj
        raise HTTPException(status_code=422, detail=sanitize(error_detail))


# ─── AQICN cache ──────────────────────────────────────────────
# Keyed by user-supplied city names, so it is bounded: an unbounded dict here
# is a memory-exhaustion vector (one entry per distinct name a client asks for).
_city_cache: dict = {}
_city_ts:    dict = {}
CACHE_TTL = 600            # seconds
CACHE_MAX_ENTRIES = 500
MAX_CITY_LEN = 100


def _cache_put(key: str, value: dict, now: float) -> None:
    if len(_city_cache) >= CACHE_MAX_ENTRIES and key not in _city_cache:
        oldest = min(_city_ts, key=_city_ts.get)
        _city_cache.pop(oldest, None)
        _city_ts.pop(oldest, None)
    _city_cache[key], _city_ts[key] = value, now


async def fetch_city_data(city: str) -> Optional[dict]:
    key = city.lower().strip()
    if not key or len(key) > MAX_CITY_LEN:
        return None
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

    # quote(): a city like "x/../y?token=z" must not alter the upstream path/query.
    url = f"https://api.waqi.info/feed/{quote(key, safe='')}/"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, params={"token": AQICN_TOKEN})
            resp.raise_for_status()
            data = resp.json()

        if data.get("status") != "ok":
            log.warning("AQICN returned non-ok for city=%r", key)
            return None

        d = data["data"]
        iaqi = d.get("iaqi", {})
        readings = {k: iaqi.get(k, {}).get("v") for k in ("pm25", "pm10", "no2", "o3", "co", "so2")}
        hri = calculate_hri(readings)
        level = hri_level(hri)
        city_name = d.get("city", {}).get("name", key)
        geo_pt = d.get("city", {}).get("geo", [0, 0])
        attributions = d.get("attributions") or [{}]

        record = {
            "bxp_version": BXP_VERSION,
            "record_id":   hashlib.sha256(f"{city_name}{time.time()}".encode()).hexdigest()[:16],
            "node_id":     NODE_ID,
            "timestamp":   datetime.now(timezone.utc).isoformat(),
            "location": {
                "name":      city_name,
                "query":     key,
                "latitude":  geo_pt[0] if len(geo_pt) > 0 else None,
                "longitude": geo_pt[1] if len(geo_pt) > 1 else None,
            },
            "readings": {k: v for k, v in readings.items() if v is not None},
            "bxp_hri": {"score": hri, "level": level, "color": hri_color(hri),
                        "advice": hri_advice(level)},
            "source": "AQICN",
            "aqi": d.get("aqi"),
            "dominant_pollutant": d.get("dominentpol"),
            "attribution": attributions[0].get("name", "AQICN"),
        }
        record["_etag"] = '"' + hashlib.sha256(
            json.dumps(record, sort_keys=True, default=str).encode()).hexdigest()[:32] + '"'
        _cache_put(key, record, now)
        log.info("Fetched city data city=%r hri=%.1f", key, hri)
        return record
    except httpx.HTTPStatusError as e:
        log.warning("AQICN HTTP error city=%r status=%s", key, e.response.status_code)
    except Exception as e:  # network/JSON errors must not become a 500 for the caller
        log.error("AQICN fetch error city=%r: %s", key, e)
    return None


DEFAULT_CITIES = [
    "accra", "lagos", "delhi", "beijing", "london",
    "sao paulo", "new york", "nairobi", "jakarta", "cairo",
]


# ─── FastAPI app ──────────────────────────────────────────────

SERVER_START_TIME = time.time()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    log.info("BXP Node starting - node_id=%s", NODE_ID)
    if AQICN_TOKEN:
        asyncio.create_task(_preload_cities())
    else:
        log.warning("AQICN_TOKEN not set - live city data disabled.")
    yield


async def _preload_cities():
    """Warm the cache on startup so first requests are fast."""
    await asyncio.gather(*(fetch_city_data(c) for c in DEFAULT_CITIES), return_exceptions=True)


app = FastAPI(
    title="BXP Protocol Node",
    description="Open standard for atmospheric exposure data - https://github.com/bxpprotocol/bxp-spec",
    version="2.1.0",
    docs_url="/docs",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["ETag"],
)


def _auth_device(authorization: Optional[str]) -> Optional[str]:
    """Device UUID for a valid `Bearer` token; None if no header; 401 if present but invalid."""
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    device = validate_token(token.strip()) if scheme.lower() == "bearer" and token.strip() else None
    if not device:
        raise HTTPException(status_code=401, detail="Invalid or expired device token.")
    return device


def _require_geohash(geohash: str, min_len: int = 5) -> None:
    if not geo.is_valid_geohash(geohash, min_len=min_len):
        raise HTTPException(
            status_code=400,
            detail=f"Geohash must be {min_len}-12 characters from 0123456789bcdefghjkmnpqrstuvwxyz.")


# ─── Routes ───────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def root():
    return HTMLResponse(pages.LANDING_PAGE)


@app.get("/bxp/v2/health")
async def health():
    uptime_s = int(time.time() - SERVER_START_TIME)
    h, r = divmod(uptime_s, 3600)
    m, s = divmod(r, 60)
    cnt = reading_count()
    uptime = f"{h}h {m}m {s}s"
    return {
        "status": "ok", "bxpVersion": BXP_VERSION, "nodeId": NODE_ID, "nodeType": NODE_TYPE,
        "timestamp": datetime.now(timezone.utc).isoformat(), "uptime": uptime,
        "readingCount": cnt, "cachedLocations": len(_city_cache), "aqicnEnabled": bool(AQICN_TOKEN),
        "data": {"bxpVersion": BXP_VERSION, "nodeType": NODE_TYPE,
                 "readingCount": cnt, "uptime": uptime},
        "spec": "https://github.com/bxpprotocol/bxp-spec",
        "doi": "https://doi.org/10.5281/zenodo.18906812",
    }


# ─── City lookup ──────────────────────────────────────────────

@app.get("/bxp/v2/city/{city}")
async def get_city(city: str, request: Request, response: Response):
    if not await _rl_city.check(_client_ip(request)):
        raise HTTPException(status_code=429, detail="Rate limit exceeded - 60 requests/minute")

    data = await fetch_city_data(city)
    if not data:
        raise HTTPException(status_code=404,
                            detail=f"No data found for '{city[:MAX_CITY_LEN]}'. Try a different city name.")
    if data.get("_noToken"):
        raise HTTPException(status_code=503, detail=data["error"])

    etag = data.get("_etag", "")
    if etag:
        if request.headers.get("if-none-match", "") == etag:
            return Response(status_code=304, headers={"ETag": etag})
        response.headers["ETag"] = etag
    return {k: v for k, v in data.items() if not k.startswith("_")}


# ─── Readings collection ──────────────────────────────────────

@app.get("/bxp/v2/readings")
async def get_readings(
    geohash:  Optional[str] = None,
    from_ts:  Optional[int] = None,
    to_ts:    Optional[int] = None,
    agent:    Optional[str] = None,
    quality:  Optional[str] = None,
    limit:    int = Query(50, ge=1, le=200),
    offset:   int = Query(0, ge=0),
    format:   Optional[str] = None,
    compress: bool = False,
):
    """
    List stored readings (offset pagination). With no filters, returns live
    data for the default cities. format=binary returns one binary `.bxp`
    container (SPEC.md 5.4, fileType="aggregate") wrapping {"readings": [...]}.
    """
    if geohash is not None:
        _require_geohash(geohash, min_len=1)

    if any(v is not None for v in (geohash, from_ts, to_ts, agent, quality)):
        results, total = query_readings(geohash=geohash, from_ts=from_ts, to_ts=to_ts,
                                        agent=agent, quality=quality, limit=limit, offset=offset)
        if format == "binary":
            return _binary_response(
                {"readings": results, "total": total, "offset": offset, "limit": limit},
                file_type="aggregate", compress=compress)
        return {"status": "ok", "count": len(results), "total": total,
                "offset": offset, "limit": limit, "data": {"readings": results}}

    results = []
    for city in DEFAULT_CITIES:
        data = await fetch_city_data(city)
        if data and not data.get("_noToken"):
            results.append({k: v for k, v in data.items() if not k.startswith("_")})

    if not results and not AQICN_TOKEN:
        return {"status": "ok", "count": 0, "data": {"readings": []},
                "notice": "AQICN_TOKEN not set. Set this environment variable to see live global data."}
    if format == "binary":
        return _binary_response({"readings": results}, file_type="aggregate", compress=compress)
    return {"status": "ok", "count": len(results), "data": {"readings": results}}


@app.get("/bxp/v2/readings/{reading_id}")
async def get_reading_by_id(reading_id: str, format: Optional[str] = None, compress: bool = False):
    """format=binary returns the reading as a binary `.bxp` container (fileType="reading")."""
    rec = get_reading(reading_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Reading not found.")
    if format == "binary":
        return _binary_response(rec, file_type="reading", compress=compress)
    return {"status": "ok", "data": {"reading": rec}}


def _duration_bucket(duration_s: Optional[int]) -> str:
    if duration_s and duration_s >= 86400:
        return "24h"
    if duration_s and duration_s >= 28800:
        return "8h"
    return "1h"


@app.post("/bxp/v2/readings", status_code=201)
async def submit_readings(request: Request, authorization: Optional[str] = Header(None)):
    """
    Accept BXP readings as JSON (SPEC.md 2) or a binary `.bxp` container
    (SPEC.md 5.1/5.2, auto-detected by magic number). The batch is stored
    atomically; a reading whose ID already exists is reported, never overwritten.

    Ownership: an authenticated device may only submit under its own UUID, and
    a UUID that belongs to a registered device can only be used with that
    device's token. Otherwise anyone could plant readings under (or claim the
    deletion rights of) someone else's device.
    """
    if not await _rl_submit.check(_client_ip(request)):
        raise HTTPException(status_code=429, detail="Rate limit exceeded - 30 submissions/minute")

    body = await _parse_submit_body(request)
    if not body.readings:
        raise HTTPException(status_code=400, detail="No readings provided.")
    authed_device = _auth_device(authorization)

    now_us = int(time.time() * 1_000_000)
    records, seen_ids = [], set()
    for raw in body.readings:
        if authed_device and raw.deviceUuid and raw.deviceUuid != authed_device:
            raise HTTPException(status_code=403,
                                detail="deviceUuid does not match the authenticated device.")
        if not authed_device and raw.deviceUuid and is_registered_device(raw.deviceUuid):
            raise HTTPException(status_code=403,
                                detail="deviceUuid belongs to a registered device; a valid token is required.")

        readings_dict: dict = {}
        for agent in raw.agents:
            key = AGENT_ID_MAP.get(agent.agentId.upper())
            if key:
                readings_dict[key] = agent.value

        hri = calculate_hri(readings_dict, _duration_bucket(raw.durationS), "general")
        ts_us = raw.timestampUs or now_us
        
        # SPEC.md 9.1: anonymous submissions are stored at precision-5 only,
        # their exact coordinates are coarsened to that cell's centre.
        if authed_device:
            lat, lon = raw.latitude, raw.longitude
            stored_geohash = geo.encode_geohash(lat, lon, 7)
            device_uuid = authed_device
        else:
            stored_geohash = geo.encode_geohash(raw.latitude, raw.longitude, geo.STORED_PRECISION_FLOOR)
            lat, lon = geo.cell_center(stored_geohash)
            # Deterministic device ID for anonymous: hash of coarsened location + timestamp
            device_uuid = "anon_" + hashlib.sha256(
                f"{stored_geohash}:{ts_us}".encode()
            ).hexdigest()[:16]
        
        # reading_id from STORED values (not raw) so duplicates are detected
        reading_id = hashlib.sha256(
            json.dumps([device_uuid, ts_us, lat, lon,
                        [(a.agentId, a.value) for a in raw.agents]]).encode()
        ).hexdigest()[:16]
        if reading_id in seen_ids:
            continue
        seen_ids.add(reading_id)

        quality = assess_quality(readings_dict, ts_us)
        record = {
            "readingId": reading_id, "bxpVersion": BXP_VERSION, "nodeId": NODE_ID,
            "deviceUuid": device_uuid,
            "timestamp": datetime.now(timezone.utc).isoformat(), "timestampUs": ts_us,
            "latitude": lat, "longitude": lon, "geohash": stored_geohash,
            "location": {"latitude": lat, "longitude": lon, "geohash": stored_geohash},
            "readings": readings_dict,
            "agents": [a.model_dump() for a in raw.agents],
            "bxpHri": hri, "bxpHriLevel": hri_level(hri),
            "quality": quality, "qualityFlag": quality["flag"],
            "durationS": raw.durationS, "indoorOutdoor": raw.indoorOutdoor,
        }
        # Unknown top-level fields (`ext`, `context`, ...) are preserved (SPEC.md 5.7/5.9).
        for extra_key in ("ext", "context", "signature"):
            if extra_key in (raw.model_extra or {}):
                record[extra_key] = raw.model_extra[extra_key]
        record["payloadHash"] = canonical_payload_hash(record)
        records.append(record)

    stored = insert_readings(records)
    if authed_device and any(stored):
        bump_device_seen(authed_device, max(r["timestampUs"] for r, ok in zip(records, stored) if ok),
                         count=sum(stored))
    for r, ok in zip(records, stored):
        r["stored"] = ok
        log.info("Reading %s id=%s hri=%.1f quality=%s",
                 "stored" if ok else "duplicate", r["readingId"], r["bxpHri"], r["qualityFlag"])
    return {"status": "ok", "data": {"readings": records}}


@app.delete("/bxp/v2/readings/{reading_id}")
async def delete_reading_endpoint(reading_id: str, authorization: Optional[str] = Header(None)):
    """
    Delete a reading with cryptographic proof (SPEC.md 9). The authenticated
    device must be the one that submitted it. The reading's content is erased;
    only a tombstone remains so the deletion replicates to peers.
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header required for deletion.")
    authed = _auth_device(authorization)

    existing = get_reading(reading_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Reading not found.")
    if existing.get("deviceUuid") != authed:
        raise HTTPException(status_code=403,
                            detail="This token does not own the reading it is trying to delete.")
    proof = delete_reading(reading_id)
    if proof is None:
        raise HTTPException(status_code=404, detail="Reading not found.")
    log.info("Reading deleted id=%s", reading_id)
    return {"status": "ok", "readingId": reading_id, "deleted": True, "deletionProof": proof,
            "message": "Reading deleted per BXP section 9."}


@app.get("/bxp/v2/readings/{reading_id}/verify")
async def verify_reading_endpoint(reading_id: str):
    result = verify_reading(reading_id)
    if not result:
        raise HTTPException(status_code=404, detail="Reading not found.")
    return {"status": "ok", "data": result}


# ─── Location endpoints ───────────────────────────────────────

@app.get("/bxp/v2/locations/{geohash}/latest")
async def get_location_latest(geohash: str):
    _require_geohash(geohash)
    rec = get_geohash_latest(geohash)
    if not rec:
        raise HTTPException(status_code=404, detail=f"No readings for geohash '{geohash}'.")
    return {"status": "ok", "data": {"reading": rec, "bxpHri": rec["bxpHri"]}}


@app.get("/bxp/v2/locations/{geohash}/history")
async def get_location_history(geohash: str, limit: int = Query(50, ge=1, le=200)):
    _require_geohash(geohash)
    records = get_geohash_history(geohash, limit)
    return {"status": "ok", "count": len(records), "data": {"readings": records}}


@app.get("/bxp/v2/locations/{geohash}/aggregate")
async def get_location_aggregate(geohash: str, from_ts: Optional[int] = None,
                                 to_ts: Optional[int] = None):
    """Privacy-safe aggregate (SPEC.md 9): only returned when >= 5 readings contribute."""
    _require_geohash(geohash)
    agg = get_aggregate(geohash, from_ts, to_ts)
    if not agg:
        raise HTTPException(status_code=404,
                            detail="Insufficient data. Aggregate requires >=5 readings (k-anonymity, SPEC.md 9).")
    return {"status": "ok", "data": agg}


# ─── Search / nearby ──────────────────────────────────────────

@app.get("/bxp/v2/search")
async def search(
    q:      Optional[str]   = None,
    lat:    Optional[float] = Query(None, ge=-90, le=90),
    lon:    Optional[float] = Query(None, ge=-180, le=180),
    limit:  int = Query(20, ge=1, le=100),
):
    """Search by city name (live AQICN data) and/or coordinates (stored readings in that cell)."""
    results = []
    if q:
        city_data = await fetch_city_data(q)
        if city_data and not city_data.get("_noToken"):
            results.append({k: v for k, v in city_data.items() if not k.startswith("_")})
    if lat is not None and lon is not None:
        db_results, _ = query_readings(geohash=geo.encode_geohash(lat, lon, 5), limit=limit)
        results.extend(db_results)
    return {"status": "ok", "count": len(results[:limit]), "data": {"results": results[:limit]}}


@app.get("/bxp/v2/nearby")
async def get_nearby(
    lat: float = Query(..., ge=-90, le=90, allow_inf_nan=False),
    lon: float = Query(..., ge=-180, le=180, allow_inf_nan=False),
    radiusM: int = Query(2000, ge=1, le=50_000),
    maxAgeS: int = Query(3600, ge=1, le=30 * 86400),
    agent: Optional[str] = None,
    minQuality: str = "UNVALIDATED",
    limit: int = Query(1, ge=1, le=50),
):
    """
    Relevance-ranked "closest useful observation" lookup (SPEC.md 7 Stage 6,
    8.2.1) for a caller with no sensor of their own. Ranking blends distance,
    freshness and quality; see database.get_nearby_readings.
    """
    if minQuality.upper() not in QUALITY_RANK:
        raise HTTPException(status_code=422, detail=f"minQuality must be one of {sorted(QUALITY_RANK)}.")
    results = get_nearby_readings(lat=lat, lon=lon, radius_m=radiusM, max_age_s=maxAgeS,
                                  agent=agent, min_quality=minQuality, limit=limit)
    return {"status": "ok", "count": len(results), "data": {"readings": results}}


# ─── Community reports ────────────────────────────────────────

@app.post("/bxp/v2/community/reports", status_code=201)
async def submit_report(body: CommunityReportRequest, request: Request):
    if not await _rl_submit.check(_client_ip(request)):
        raise HTTPException(status_code=429, detail="Rate limit exceeded.")
    now = time.time()
    gh = geo.encode_geohash(body.latitude, body.longitude, geo.STORED_PRECISION_FLOOR)
    lat, lon = geo.cell_center(gh)   # never persist the exact position (SPEC.md 9.1)
    report = {
        "reportId": secrets.token_hex(8), "geohash": gh, "latitude": lat, "longitude": lon,
        "timestamp": datetime.fromtimestamp(now, timezone.utc).isoformat(),
        "timestampUs": int(now * 1_000_000), "reportType": body.reportType,
        "description": body.description, "severity": body.severity,
        "submitterHash": body.submitterHash,
    }
    insert_report(report)
    return {"status": "ok", "data": {"report": report}}


@app.get("/bxp/v2/community/reports")
async def get_reports(geohash: Optional[str] = None, limit: int = Query(50, ge=1, le=200)):
    if geohash is not None:
        _require_geohash(geohash, min_len=1)
    reports = query_reports(geohash, limit)
    return {"status": "ok", "count": len(reports), "data": {"reports": reports}}


# ─── Device registration ──────────────────────────────────────

@app.post("/bxp/v2/devices/register", status_code=201)
async def register_device_endpoint(body: DeviceRegisterRequest, request: Request):
    if not await _rl_register.check(_client_ip(request)):
        raise HTTPException(status_code=429, detail="Rate limit exceeded - 5 registrations/minute.")
    dev_uuid = body.deviceUuid or str(uuid.uuid4())
    raw_token = "bxp_" + secrets.token_hex(24)   # 192 bits from the OS CSPRNG
    token_hash = "sha256:" + hashlib.sha256(raw_token.encode()).hexdigest()
    try:
        device = register_device(dev_uuid, token_hash, label=body.label, owner_hash=body.ownerHash)
    except DeviceExistsError:
        raise HTTPException(status_code=409, detail="deviceUuid is already in use.") from None
    log.info("Device registered uuid=%s", dev_uuid)
    return {"status": "ok", "data": {
        "device": device, "token": raw_token,
        "notice": "Store this token securely. It will not be shown again."}}


@app.get("/bxp/v2/devices/{device_uuid}")
async def get_device_endpoint(device_uuid: str):
    device = get_device(device_uuid)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found.")
    return {"status": "ok", "data": {"device": device}}


# ─── Federated nodes ──────────────────────────────────────────

@app.get("/bxp/v2/nodes")
async def list_nodes():
    nodes = get_nodes(active_only=True)
    return {"status": "ok", "count": len(nodes), "data": {"nodes": nodes}}


class NodeAnnounceRequest(BaseModel):
    nodeId:       str = Field(pattern=_ID_PATTERN)
    baseUrl:      str = Field(min_length=8, max_length=256)
    bxpVersion:   str = Field(default="2.0", max_length=16)
    nodeType:     str = Field(default="unknown", max_length=32)
    readingCount: int = Field(default=0, ge=0, le=10**12)


def _valid_base_url(url: str) -> bool:
    parts = urlsplit(url)
    return parts.scheme in ("http", "https") and bool(parts.hostname) and not parts.username


@app.post("/bxp/v2/nodes/announce")
async def announce_node(body: NodeAnnounceRequest, request: Request):
    """
    Register a peer node so it appears in GET /nodes. This is a directory
    entry only - this server never fetches the announced URL - and a node_id
    cannot be re-pointed at a different baseUrl (see database.upsert_node).
    """
    if not await _rl_register.check(_client_ip(request)):
        raise HTTPException(status_code=429, detail="Rate limit exceeded.")
    if not _valid_base_url(body.baseUrl):
        raise HTTPException(status_code=422, detail="baseUrl must be an http(s) URL.")
    try:
        upsert_node(body.nodeId, body.baseUrl.rstrip("/"), body.bxpVersion,
                    body.nodeType, body.readingCount)
    except NodeRegistryError as e:
        raise HTTPException(status_code=409, detail=str(e)) from None
    return {"status": "ok", "message": "Node registered."}


@app.get("/bxp/v2/sync")
async def sync_pull(
    since: int = Query(0, ge=0),
    limit: int = Query(500, ge=1, le=2000),
    authorization: Optional[str] = Header(None),
):
    """
    Federation pull (SPEC.md 7 Stage 7, 8.2.2). Returns every change after the
    opaque cursor `since` (default 0 = from the beginning), oldest first, plus
    `nextCursor` to resume from. Deleted readings arrive as tombstones
    ({"readingId", "deleted": true, "deletionProof"}) that a replica must apply.

    The cursor is the node's ingest sequence, not an observation timestamp, so
    late-arriving readings are never skipped and a bogus far-future timestamp
    cannot stall replication. Each reading carries its originating `nodeId`.
    Gated by BXP_NODE_SYNC_TOKEN when set; trust, dedup across multiple peers
    and conflict resolution are deferred (SPEC.md 7 Stage 7).
    """
    if BXP_NODE_SYNC_TOKEN:
        scheme, _, token = (authorization or "").partition(" ")
        supplied = token.strip() if scheme.lower() == "bearer" else ""
        if not hmac.compare_digest(supplied.encode(), BXP_NODE_SYNC_TOKEN.encode()):
            raise HTTPException(status_code=401, detail="Invalid or missing node token.")
    items, next_cursor = get_readings_since(since, limit)
    return {"status": "ok", "count": len(items), "data": {"readings": items},
            "nextCursor": next_cursor}


# ─── Prometheus metrics ───────────────────────────────────────

_LABEL_UNSAFE = re.compile(r'[\\"\n]')


@app.get("/metrics", response_class=PlainTextResponse)
async def metrics():
    """Prometheus-compatible metrics."""
    label = lambda v: _LABEL_UNSAFE.sub("_", str(v))  # noqa: E731 - node id comes from env; keep the exposition format valid
    lines = [
        "# HELP bxp_readings_total Stored readings (non-deleted)",
        "# TYPE bxp_readings_total gauge",
        f"bxp_readings_total {reading_count()}",
        "",
        "# HELP bxp_uptime_seconds Server uptime in seconds",
        "# TYPE bxp_uptime_seconds gauge",
        f"bxp_uptime_seconds {time.time() - SERVER_START_TIME:.1f}",
        "",
        "# HELP bxp_city_cache_size Number of cached city responses",
        "# TYPE bxp_city_cache_size gauge",
        f"bxp_city_cache_size {len(_city_cache)}",
        "",
        "# HELP bxp_info BXP node information",
        "# TYPE bxp_info gauge",
        f'bxp_info{{node_id="{label(NODE_ID)}",bxp_version="{BXP_VERSION}",'
        f'node_type="{label(NODE_TYPE)}"}} 1',
    ]
    return "\n".join(lines) + "\n"


# ─── Widget & dashboard pages ─────────────────────────────────

@app.get("/widget/{city}", response_class=HTMLResponse)
async def widget(city: str):
    """Embeddable iframe widget."""
    data = await fetch_city_data(city)
    if not data or data.get("_noToken"):
        return HTMLResponse(pages.widget_missing_page(city[:MAX_CITY_LEN]))
    return HTMLResponse(pages.widget_page(data, city[:MAX_CITY_LEN]))


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_home():
    return HTMLResponse(pages.SEARCH_PAGE)


@app.get("/map", response_class=HTMLResponse)
async def map_view():
    return HTMLResponse(pages.MAP_PAGE)


@app.get("/compare", response_class=HTMLResponse)
async def compare_view():
    return HTMLResponse(pages.COMPARE_PAGE)


@app.get("/dashboard/{city}", response_class=HTMLResponse)
async def dashboard(city: str):
    data = await fetch_city_data(city)
    if not data or data.get("_noToken"):
        msg = data["error"] if data else f'No air quality data available for "{city[:MAX_CITY_LEN]}"'
        return HTMLResponse(pages.not_found_page(msg))
    return HTMLResponse(pages.render_dashboard(data))


if __name__ == "__main__":
    uvicorn.run("server:app", host=os.environ.get("BXP_HOST", "0.0.0.0"),
                port=int(os.environ.get("BXP_PORT", "5000")), reload=False)
