# BXP — Breathe Exposure Protocol
## Specification v2.0

**Status:** Draft  
**License:** Apache 2.0  
**Author:** Elvarin  
**Repository:** https://github.com/bxpprotocol/bxp-spec  

---

## 1. Introduction

BXP (Breathe Exposure Protocol) is an open file format and data exchange
protocol for recording, storing, and transmitting human atmospheric
exposure data over time.

BXP defines:
- A file format (.bxp / .bxp.json)
- A REST API for reading submission and retrieval
- A data model for atmospheric agents
- A composite Health Risk Index (BXP_HRI)
- A geographic file system based on geohash
- A privacy framework for personal exposure data

BXP is designed to be:
- **Universal** — any sensor, platform, or geography
- **Open** — Apache 2.0, no fees, no gatekeepers
- **Interoperable** — any BXP system reads any BXP file
- **Extensible** — versioned, backward-compatible

---

## 2. The .bxp File Format

A .bxp file is a JSON document representing one or more atmospheric
exposure readings.

### 2.1 Minimal Valid Record

```json
{
  "bxpVersion": "2.0",
  "deviceUuid": "550e8400-e29b-41d4-a716-446655440000",
  "geohash": "s1v0g",
  "timestampUs": 1741342800000000,
  "agents": [
    { "agentId": "PM2_5", "value": 47.2, "unit": "ug/m3" }
  ],
  "quality": { "flag": "VALIDATED", "confidence": 0.95 }
}
```

### 2.2 Full Record Schema

```json
{
  "bxpVersion": "2.0",
  "deviceUuid": "string (UUID v4)",
  "geohash": "string (min precision 5)",
  "latitude": "number",
  "longitude": "number",
  "altitudeM": "number (optional)",
  "timestampUs": "integer (Unix epoch microseconds UTC)",
  "durationS": "integer (measurement duration seconds)",
  "indoorOutdoor": "outdoor | indoor",
  "agents": [
    {
      "agentId": "string",
      "value": "number",
      "unit": "string"
    }
  ],
  "context": {
    "weather": "string (optional)",
    "activityType": "string (optional)",
    "nearbySource": "string (optional)"
  },
  "quality": {
    "flag": "VALIDATED | UNVALIDATED | SUSPECT | INVALID",
    "confidence": "number 0.0-1.0",
    "qcMethod": "string"
  },
  "bxpHri": "number 0-100 (calculated)",
  "bxpHriLevel": "CLEAN | MODERATE | ELEVATED | HIGH | VERY_HIGH | HAZARDOUS",
  "payloadHash": "string (sha256:...)"
}
```

---

## 3. Atmospheric Agents

| Agent ID | Name                  | Unit    | WHO 24h Limit |
|----------|-----------------------|---------|---------------|
| PM1      | Particulate <1μm      | μg/m³   | —             |
| PM2_5    | Fine Particulate      | μg/m³   | 15            |
| PM10     | Coarse Particulate    | μg/m³   | 45            |
| BC       | Black Carbon          | μg/m³   | —             |
| CO       | Carbon Monoxide       | ppm     | 4             |
| CO2      | Carbon Dioxide        | ppm     | —             |
| NO2      | Nitrogen Dioxide      | ppb     | 25            |
| SO2      | Sulphur Dioxide       | ppb     | 40            |
| O3       | Ground-level Ozone    | ppb     | 100           |
| H2S      | Hydrogen Sulphide     | ppb     | 7             |
| NH3      | Ammonia               | ppm     | 25            |
| TVOC     | Total VOCs            | ppb     | 500           |
| BENZ     | Benzene               | ppb     | 1             |
| FORM     | Formaldehyde          | ppb     | 8             |
| TEMP     | Temperature           | °C      | —             |
| RH       | Relative Humidity     | %       | —             |
| PRESS    | Atmospheric Pressure  | hPa     | —             |
| UV       | UV Index              | index   | —             |
| PB       | Lead                  | μg/m³   | 0.5           |

---

## 4. BXP Health Risk Index (BXP_HRI)

BXP_HRI is a composite score from 0–100 representing overall
atmospheric health risk based on WHO 2021 Air Quality Guidelines.

### 4.1 Calculation

For each available agent:
1. Normalize: `agent_risk = min(1.0, value / WHO_threshold)`
2. Weight by WHO DALY burden
3. Sum: `raw_hri = Σ(agent_risk × weight)`
4. Apply duration factor (1h=1.0, 8h=1.2, 24h=1.5)
5. Apply population factor (general=1.0, sensitive=1.3)
6. Scale: `BXP_HRI = min(100, raw_hri × 100 × duration × population)`

### 4.2 Risk Levels

| Score  | Level      | Color   | Action                              |
|--------|------------|---------|-------------------------------------|
| 0–20   | CLEAN      | #00C851 | No restrictions                     |
| 21–40  | MODERATE   | #FFBB33 | Sensitive groups limit exertion     |
| 41–60  | ELEVATED   | #FF8800 | Reduce outdoor exertion             |
| 61–75  | HIGH       | #CC0000 | Wear N95, close windows             |
| 76–90  | VERY_HIGH  | #9B0000 | Avoid outdoors                      |
| 91–100 | HAZARDOUS  | #4A0000 | Emergency — stay indoors            |

---

## 5. REST API

Base URL: `https://[host]/bxp/v2/`

### 5.1 Submit Readings

```
POST /readings
Authorization: Bearer {device_token}
Content-Type: application/json

Body: BXP container with one or more readings

Response 201:
{
  "status": "ok",
  "bxpVersion": "2.0",
  "data": { "readingId": "uuid", "bxpHri": 61, "level": "HIGH" }
}
```

### 5.2 Get Readings

```
GET /readings
Query: geohash, from, to, agent, quality
Response 200: { "data": { "readings": [...] } }
```

### 5.3 Get Reading by ID

```
GET /readings/{id}
Response 200: { "data": { "reading": {...} } }
```

### 5.4 Get Latest for Location

```
GET /locations/{geohash}/latest
Response 200: { "data": { "reading": {...}, "bxpHri": 61 } }
```

### 5.5 Health Check

```
GET /health
Response 200: { "status": "ok", "bxpVersion": "2.0" }
```

---

## 6. Quality Flags

| Flag        | Meaning                                        |
|-------------|------------------------------------------------|
| VALIDATED   | Passed all QC checks, cross-validated          |
| UNVALIDATED | Submitted, basic checks passed, not cross-val  |
| SUSPECT     | Failed one or more QC checks                   |
| INVALID     | Failed critical checks, should not be used     |

---

## 7. Geohash Geographic System

BXP uses geohash encoding for all geographic references.

| Precision | Cell Size     | Use Case              |
|-----------|---------------|-----------------------|
| 5         | ~4.9 km       | District level        |
| 6         | ~1.2 km       | Neighborhood level    |
| 7         | ~153 m        | Street block          |
| 8         | ~38 m         | Building level        |
| 9         | ~4.8 m        | High precision        |

Minimum required precision: 5

---

## 8. Versioning

BXP uses semantic versioning: MAJOR.MINOR.PATCH

- PATCH: bug fixes, clarifications — no compatibility impact
- MINOR: new optional fields — full backward compatibility
- MAJOR: breaking changes — 18 months notice required

---

## 9. Privacy

- Person identifiers stored as SHA-256 hashes only
- Personal records default to geohash-5 precision
- Aggregates require minimum k=5 sources
- Users may request full deletion at any time
- Deletion is cryptographically verifiable

---

## 10. License

Apache 2.0 — free to use, implement, modify, distribute.
No royalties. No restrictions. No gatekeepers.
