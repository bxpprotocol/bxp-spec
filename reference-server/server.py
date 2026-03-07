"""
BXP Reference Server v2.0
Breathe Exposure Protocol — Reference Node Implementation

Run:
    pip install -r requirements.txt
    python server.py

API Base: http://localhost:8000/bxp/v2/
Docs:     http://localhost:8000/docs
"""

from fastapi import FastAPI, HTTPException, Header, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional, List
import uuid
import time
import hashlib
import json
from datetime import datetime, timezone

# ─────────────────────────────────────────────────────────────
# BXP_HRI ENGINE
# ─────────────────────────────────────────────────────────────

WHO_THRESHOLDS = {
    "PM2_5": 15.0, "PM10": 45.0, "NO2": 25.0,
    "O3": 100.0,   "CO": 4.0,    "SO2": 40.0,
    "TVOC": 500.0, "BENZ": 1.0,  "FORM": 8.0,
}

HRI_WEIGHTS = {
    "PM2_5": 0.35, "PM10": 0.15, "NO2": 0.15,
    "O3": 0.12,    "CO": 0.10,   "SO2": 0.05,
    "TVOC": 0.04,  "BENZ": 0.02, "FORM": 0.02,
}

RISK_LEVELS = [
    (0,  20,  "CLEAN",     "#00C851"),
    (21, 40,  "MODERATE",  "#FFBB33"),
    (41, 60,  "ELEVATED",  "#FF8800"),
    (61, 75,  "HIGH",      "#CC0000"),
    (76, 90,  "VERY_HIGH", "#9B0000"),
    (91, 100, "HAZARDOUS", "#4A0000"),
]


def calculate_hri(agents: list, duration: str = "1h",
                  population: str = "general") -> dict:
    raw = 0.0
    breakdown = {}
    d_factor = {"1h": 1.0, "8h": 1.2, "24h": 1.5}.get(duration, 1.0)
    v_factor = {"general": 1.0, "sensitive": 1.3}.get(population, 1.0)

    for a in agents:
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
            "value": val, "threshold": thr,
            "normalizedRisk": round(risk, 4),
            "contribution": round(contrib, 4),
            "exceedsWho": float(val) > thr
        }

    score = round(min(100.0, raw * 100 * d_factor * v_factor), 2)
    level = color = "CLEAN"
    for lo, hi, ln, lc in RISK_LEVELS:
        if lo <= score <= hi:
            level, color = ln, lc
            break

    return {"score": score, "level": level,
            "color": color, "breakdown": breakdown}


# ─────────────────────────────────────────────────────────────
# GEOHASH ENCODER
# ─────────────────────────────────────────────────────────────

BASE32 = "0123456789bcdefghjkmnpqrstuvwxyz"


def encode_geohash(lat: float, lon: float, precision: int = 7) -> str:
    lat_range = [-90.0,  90.0]
    lon_range = [-180.0, 180.0]
    bits = [16, 8, 4, 2, 1]
    bit_idx = 0
    even = True
    result = ""
    ch = 0
    while len(result) < precision:
        if even:
            mid = (lon_range[0] + lon_range[1]) / 2
            if lon >= mid:
                ch |= bits[bit_idx]
                lon_range[0] = mid
            else:
                lon_range[1] = mid
        else:
            mid = (lat_range[0] + lat_range[1]) / 2
            if lat >= mid:
                ch |= bits[bit_idx]
                lat_range[0] = mid
            else:
                lat_range[1] = mid
        even = not even
        if bit_idx < 4:
            bit_idx += 1
        else:
            result += BASE32[ch]
            bit_idx = 0
            ch = 0
    return result


# ─────────────────────────────────────────────────────────────
# PYDANTIC MODELS
# ─────────────────────────────────────────────────────────────

class AgentReading(BaseModel):
    agentId: str
    value:   float
    unit:    str = "canonical"


class QualityInfo(BaseModel):
    flag:       str = "UNVALIDATED"
    confidence: float = 0.8
    qcMethod:   str = "automated-v2"


class BXPReading(BaseModel):
    deviceUuid:    str = Field(default_factory=lambda: str(uuid.uuid4()))
    geohash:       Optional[str] = None
    latitude:      Optional[float] = None
    longitude:     Optional[float] = None
    altitudeM:     Optional[float] = None
    timestampUs:   Optional[int]   = None
    durationS:     int = 60
    indoorOutdoor: str = "outdoor"
    agents:        List[AgentReading]
    context:       Optional[dict] = None
    quality:       Optional[QualityInfo] = None


class SubmitRequest(BaseModel):
    readings: List[BXPReading]


# ─────────────────────────────────────────────────────────────
# IN-MEMORY STORE
# ─────────────────────────────────────────────────────────────

STORE: dict[str, dict] = {}


def store_reading(reading: BXPReading) -> dict:
    rid    = str(uuid.uuid4())
    now_us = int(time.time() * 1_000_000)

    geohash = reading.geohash
    if not geohash and reading.latitude and reading.longitude:
        geohash = encode_geohash(reading.latitude, reading.longitude, 7)

    agents_list = [a.model_dump() for a in reading.agents]
    hri = calculate_hri(agents_list)

    record = {
        "id":            rid,
        "bxpVersion":    "2.0",
        "deviceUuid":    reading.deviceUuid,
        "geohash":       geohash or "unknown",
        "latitude":      reading.latitude,
        "longitude":     reading.longitude,
        "altitudeM":     reading.altitudeM,
        "timestampUs":   reading.timestampUs or now_us,
        "durationS":     reading.durationS,
        "indoorOutdoor": reading.indoorOutdoor,
        "agents":        agents_list,
        "context":       reading.context,
        "quality": {
            "flag":       (reading.quality.flag if reading.quality else "UNVALIDATED"),
            "confidence": (reading.quality.confidence if reading.quality else 0.8),
            "qcMethod":   "automated-v2"
        },
        "bxpHri":      hri["score"],
        "bxpHriLevel": hri["level"],
        "bxpHriColor": hri["color"],
        "createdAt":   datetime.now(timezone.utc).isoformat(),
    }

    payload_str = json.dumps(
        {k: v for k, v in record.items() if k != "payloadHash"},
        sort_keys=True, separators=(',', ':')
    )
    record["payloadHash"] = "sha256:" + hashlib.sha256(
        payload_str.encode()
    ).hexdigest()

    STORE[rid] = record
    return record


def bxp_response(data: dict, status_code: int = 200) -> dict:
    return {
        "status":     "ok",
        "bxpVersion": "2.0",
        "requestId":  str(uuid.uuid4()),
        "timestamp":  datetime.now(timezone.utc).isoformat(),
        "data":       data,
        "errors":     []
    }


def bxp_error(code: str, message: str, status: int = 400):
    return JSONResponse(status_code=status, content={
        "status":     "error",
        "bxpVersion": "2.0",
        "requestId":  str(uuid.uuid4()),
        "timestamp":  datetime.now(timezone.utc).isoformat(),
        "data":       None,
        "errors":     [{"code": code, "message": message}]
    })


# ─────────────────────────────────────────────────────────────
# FASTAPI APP
# ─────────────────────────────────────────────────────────────

app = FastAPI(
    title="BXP Reference Server",
    description=(
        "Breathe Exposure Protocol v2.0 — Reference Node Implementation. "
        "Open source, Apache 2.0. https://github.com/bxpprotocol/bxp-spec"
    ),
    version="2.0.0",
)


@app.get("/bxp/v2/health")
def health():
    return bxp_response({
        "nodeType":     "community",
        "bxpVersion":   "2.0",
        "readingCount": len(STORE),
        "uptime":       "operational"
    })


@app.post("/bxp/v2/readings", status_code=201)
def submit_readings(body: SubmitRequest):
    if not body.readings:
        return bxp_error("BXP_4001", "No readings provided")

    results = []
    for r in body.readings:
        if not r.agents:
            return bxp_error("BXP_4002", "Each reading must have at least one agent")
        record = store_reading(r)
        results.append({
            "readingId":   record["id"],
            "geohash":     record["geohash"],
            "bxpHri":      record["bxpHri"],
            "bxpHriLevel": record["bxpHriLevel"],
            "qualityFlag": record["quality"]["flag"],
        })

    return JSONResponse(status_code=201, content=bxp_response({
        "submitted": len(results),
        "readings":  results
    }))


@app.get("/bxp/v2/readings")
def get_readings(
    geohash: Optional[str] = Query(None),
    quality: Optional[str] = Query(None),
    limit:   int           = Query(100, le=1000),
    offset:  int           = Query(0)
):
    results = list(STORE.values())

    if geohash:
        results = [r for r in results
                   if r.get("geohash", "").startswith(geohash)]
    if quality:
        results = [r for r in results
                   if r.get("quality", {}).get("flag") == quality.upper()]

    results.sort(key=lambda r: r.get("timestampUs", 0), reverse=True)
    page = results[offset: offset + limit]

    return bxp_response({
        "readings":      page,
        "totalCount":    len(results),
        "returnedCount": len(page),
        "offset":        offset
    })


@app.get("/bxp/v2/readings/{reading_id}")
def get_reading(reading_id: str):
    record = STORE.get(reading_id)
    if not record:
        return bxp_error("BXP_4040", f"Reading {reading_id} not found", 404)
    return bxp_response({"reading": record})


@app.get("/bxp/v2/locations/{geohash}/latest")
def get_latest(geohash: str):
    if len(geohash) < 5:
        return bxp_error("BXP_4003", "Geohash precision must be at least 5")

    matches = [r for r in STORE.values()
               if r.get("geohash", "").startswith(geohash)]

    if not matches:
        return bxp_error("BXP_4041",
                         f"No readings found for geohash {geohash}", 404)

    latest = max(matches, key=lambda r: r.get("timestampUs", 0))
    return bxp_response({
        "geohash":     geohash,
        "reading":     latest,
        "bxpHri":      latest["bxpHri"],
        "bxpHriLevel": latest["bxpHriLevel"],
        "bxpHriColor": latest["bxpHriColor"],
    })


@app.get("/bxp/v2/locations/{geohash}/history")
def get_history(geohash: str, limit: int = Query(50, le=500)):
    if len(geohash) < 5:
        return bxp_error("BXP_4003", "Geohash precision must be at least 5")

    matches = [r for r in STORE.values()
               if r.get("geohash", "").startswith(geohash)]
    matches.sort(key=lambda r: r.get("timestampUs", 0), reverse=True)

    return bxp_response({
        "geohash":  geohash,
        "readings": matches[:limit],
        "count":    len(matches)
    })


@app.get("/bxp/v2/agents")
def get_agents():
    agents = [
        {"agentId": "PM2_5", "name": "Fine Particulate Matter",      "unit": "ug/m3", "whoLimit": 15.0,  "hriWeight": 0.35},
        {"agentId": "PM10",  "name": "Coarse Particulate Matter",    "unit": "ug/m3", "whoLimit": 45.0,  "hriWeight": 0.15},
        {"agentId": "NO2",   "name": "Nitrogen Dioxide",             "unit": "ppb",   "whoLimit": 25.0,  "hriWeight": 0.15},
        {"agentId": "O3",    "name": "Ground-level Ozone",           "unit": "ppb",   "whoLimit": 100.0, "hriWeight": 0.12},
        {"agentId": "CO",    "name": "Carbon Monoxide",              "unit": "ppm",   "whoLimit": 4.0,   "hriWeight": 0.10},
        {"agentId": "SO2",   "name": "Sulphur Dioxide",              "unit": "ppb",   "whoLimit": 40.0,  "hriWeight": 0.05},
        {"agentId": "TVOC",  "name": "Total Volatile Organic Compounds", "unit": "ppb", "whoLimit": 500.0, "hriWeight": 0.04},
        {"agentId": "BENZ",  "name": "Benzene",                      "unit": "ppb",   "whoLimit": 1.0,   "hriWeight": 0.02},
        {"agentId": "FORM",  "name": "Formaldehyde",                 "unit": "ppb",   "whoLimit": 8.0,   "hriWeight": 0.02},
        {"agentId": "TEMP",  "name": "Temperature",                  "unit": "C",     "whoLimit": None,  "hriWeight": 0},
        {"agentId": "RH",    "name": "Relative Humidity",            "unit": "%",     "whoLimit": None,  "hriWeight": 0},
        {"agentId": "PRESS", "name": "Atmospheric Pressure",         "unit": "hPa",   "whoLimit": None,  "hriWeight": 0},
        {"agentId": "UV",    "name": "UV Index",                     "unit": "index", "whoLimit": None,  "hriWeight": 0},
        {"agentId": "PM1",   "name": "Ultrafine Particulate Matter", "unit": "ug/m3", "whoLimit": None,  "hriWeight": 0},
        {"agentId": "CO2",   "name": "Carbon Dioxide",               "unit": "ppm",   "whoLimit": None,  "hriWeight": 0},
        {"agentId": "H2S",   "name": "Hydrogen Sulphide",            "unit": "ppb",   "whoLimit": 7.0,   "hriWeight": 0},
        {"agentId": "PB",    "name": "Lead",                         "unit": "ug/m3", "whoLimit": 0.5,   "hriWeight": 0},
    ]
    return bxp_response({"agents": agents, "count": len(agents)})


@app.post("/bxp/v2/hri/calculate")
def calculate_hri_endpoint(
    agents:     List[AgentReading],
    duration:   str = Query("1h"),
    population: str = Query("general")
):
    result = calculate_hri([a.model_dump() for a in agents],
                           duration, population)
    return bxp_response({"hri": result})


# ─────────────────────────────────────────────────────────────
# STARTUP — 10 Global cities sample data
# ─────────────────────────────────────────────────────────────

GLOBAL_SAMPLES = [
    {"lat":  5.6037,  "lon":  -0.1870,  "pm25":  47.2, "pm10":  62.1, "no2": 18.3, "o3": 12.0, "temp": 29.0, "rh": 78.0, "city": "Accra, Ghana",            "country": "GH", "source": "traffic"},
    {"lat":  6.5244,  "lon":   3.3792,  "pm25":  68.4, "pm10":  89.2, "no2": 44.1, "o3":  8.2, "temp": 31.0, "rh": 82.0, "city": "Lagos, Nigeria",           "country": "NG", "source": "traffic_industrial"},
    {"lat": 28.6139,  "lon":  77.2090,  "pm25": 156.3, "pm10": 228.4, "no2": 67.8, "o3":  5.1, "temp": 22.0, "rh": 45.0, "city": "Delhi, India",             "country": "IN", "source": "vehicles_crop_burning"},
    {"lat": 39.9042,  "lon": 116.4074,  "pm25":  89.7, "pm10": 134.2, "no2": 58.3, "o3": 11.4, "temp":  8.0, "rh": 38.0, "city": "Beijing, China",           "country": "CN", "source": "coal_traffic"},
    {"lat": 51.5074,  "lon":  -0.1278,  "pm25":  14.2, "pm10":  22.8, "no2": 38.1, "o3": 44.2, "temp": 12.0, "rh": 72.0, "city": "London, United Kingdom",   "country": "GB", "source": "traffic_diesel"},
    {"lat":-23.5505,  "lon": -46.6333,  "pm25":  31.8, "pm10":  48.6, "no2": 52.4, "o3": 28.7, "temp": 24.0, "rh": 68.0, "city": "Sao Paulo, Brazil",        "country": "BR", "source": "vehicles_industry"},
    {"lat": 40.7128,  "lon": -74.0060,  "pm25":  12.1, "pm10":  18.4, "no2": 29.6, "o3": 52.3, "temp": 18.0, "rh": 61.0, "city": "New York, USA",            "country": "US", "source": "traffic_urban"},
    {"lat": -1.2921,  "lon":  36.8219,  "pm25":  38.9, "pm10":  54.7, "no2": 22.1, "o3": 18.4, "temp": 20.0, "rh": 65.0, "city": "Nairobi, Kenya",           "country": "KE", "source": "traffic_cooking_fires"},
    {"lat": -6.2088,  "lon": 106.8456,  "pm25":  71.3, "pm10":  98.6, "no2": 41.7, "o3":  9.3, "temp": 33.0, "rh": 85.0, "city": "Jakarta, Indonesia",       "country": "ID", "source": "vehicles_industrial"},
    {"lat": 30.0444,  "lon":  31.2357,  "pm25":  93.4, "pm10": 187.3, "no2": 49.2, "o3":  7.8, "temp": 28.0, "rh": 35.0, "city": "Cairo, Egypt",             "country": "EG", "source": "desert_dust_traffic"},
]


@app.on_event("startup")
def load_sample_data():
    base_time = int(time.time() * 1_000_000) - (3600 * 1_000_000 * 24)
    for i, s in enumerate(GLOBAL_SAMPLES):
        r = BXPReading(
            deviceUuid=f"00000000-0000-0000-0000-{str(i+1).zfill(12)}",
            latitude=s["lat"],
            longitude=s["lon"],
            timestampUs=base_time + i * 3600 * 1_000_000,
            durationS=600,
            agents=[
                AgentReading(agentId="PM2_5", value=s["pm25"], unit="ug/m3"),
                AgentReading(agentId="PM10",  value=s["pm10"], unit="ug/m3"),
                AgentReading(agentId="NO2",   value=s["no2"],  unit="ppb"),
                AgentReading(agentId="O3",    value=s["o3"],   unit="ppb"),
                AgentReading(agentId="TEMP",  value=s["temp"], unit="C"),
                AgentReading(agentId="RH",    value=s["rh"],   unit="%"),
            ],
            context={"location": s["city"], "country": s["country"],
                     "nearbySource": s["source"]},
            quality=QualityInfo(flag="VALIDATED", confidence=0.95)
        )
        store_reading(r)

    print(f"[BXP] Loaded {len(GLOBAL_SAMPLES)} global sample readings.")
    print("[BXP] Cities: Accra, Lagos, Delhi, Beijing, London, Sao Paulo, New York, Nairobi, Jakarta, Cairo")
    print("[BXP] Server ready at http://localhost:8000/bxp/v2/")
    print("[BXP] API docs at http://localhost:8000/docs")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
