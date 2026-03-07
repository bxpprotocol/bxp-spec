# BXP API Reference v2.0

Base URL: `http://localhost:8000/bxp/v2/`
Interactive docs: `http://localhost:8000/docs`

All responses use the standard BXP envelope:
```json
{
  "status": "ok",
  "bxpVersion": "2.0",
  "requestId": "uuid",
  "timestamp": "ISO8601",
  "data": { ... },
  "errors": []
}
```

---

## POST /readings

Submit one or more readings.

**Request body:**
```json
{
  "readings": [
    {
      "deviceUuid": "550e8400-e29b-41d4-a716-446655440000",
      "latitude": 5.6037,
      "longitude": -0.1870,
      "agents": [
        { "agentId": "PM2_5", "value": 47.2, "unit": "ug/m3" },
        { "agentId": "NO2",   "value": 18.3, "unit": "ppb"   }
      ]
    }
  ]
}
```

**Response 201:**
```json
{
  "status": "ok",
  "data": {
    "submitted": 1,
    "readings": [
      {
        "readingId": "uuid",
        "geohash": "s1v0gx4",
        "bxpHri": 61.2,
        "bxpHriLevel": "HIGH",
        "qualityFlag": "UNVALIDATED"
      }
    ]
  }
}
```

---

## GET /readings

Get all readings with optional filters.

**Query parameters:**
- `geohash` — filter by geohash prefix (e.g. `s1v0`)
- `quality` — filter by quality flag (`VALIDATED`, `UNVALIDATED`, etc.)
- `limit` — max records (default 100, max 1000)
- `offset` — pagination offset

**Example:** `GET /bxp/v2/readings?geohash=s1v0&limit=10`

---

## GET /readings/{id}

Get a specific reading by ID.

**Example:** `GET /bxp/v2/readings/550e8400-e29b-41d4-a716-446655440000`

---

## GET /locations/{geohash}/latest

Get the most recent reading for a geohash location.

Minimum geohash precision: 5

**Example:** `GET /bxp/v2/locations/s1v0g/latest`

**Response:**
```json
{
  "data": {
    "geohash": "s1v0g",
    "reading": { ... },
    "bxpHri": 61.2,
    "bxpHriLevel": "HIGH",
    "bxpHriColor": "#CC0000"
  }
}
```

---

## GET /locations/{geohash}/history

Get reading history for a geohash.

**Query:** `limit` (default 50, max 500)

---

## GET /agents

List all supported atmospheric agents.

**Response:**
```json
{
  "data": {
    "agents": [
      {
        "agentId": "PM2_5",
        "name": "Fine Particulate Matter",
        "unit": "μg/m³",
        "whoLimit": 15.0,
        "hriWeight": 0.35
      }
    ],
    "count": 17
  }
}
```

---

## POST /hri/calculate

Calculate BXP_HRI from agent values.

**Query parameters:**
- `duration` — `1h` | `8h` | `24h` (default `1h`)
- `population` — `general` | `sensitive` (default `general`)

**Request body:**
```json
[
  { "agentId": "PM2_5", "value": 67.0, "unit": "ug/m3" },
  { "agentId": "NO2",   "value": 31.0, "unit": "ppb"   }
]
```

**Response:**
```json
{
  "data": {
    "hri": {
      "score": 72.4,
      "level": "HIGH",
      "color": "#CC0000",
      "breakdown": {
        "PM2_5": { "value": 67.0, "normalizedRisk": 1.0, "contribution": 0.35 },
        "NO2":   { "value": 31.0, "normalizedRisk": 0.48, "contribution": 0.072 }
      }
    }
  }
}
```

---

## GET /health

Server health check.

**Response:**
```json
{
  "status": "ok",
  "data": {
    "nodeType": "community",
    "bxpVersion": "2.0",
    "readingCount": 10,
    "uptime": "operational"
  }
}
```

---

## Error Codes

| Code      | HTTP | Meaning                              |
|-----------|------|--------------------------------------|
| BXP_4001  | 400  | No readings provided                 |
| BXP_4002  | 400  | Reading has no agents                |
| BXP_4003  | 400  | Geohash precision too low            |
| BXP_4006  | 400  | Payload hash mismatch                |
| BXP_4010  | 401  | Missing or invalid device token      |
| BXP_4030  | 403  | Device UUID mismatch                 |
| BXP_4040  | 404  | Reading not found                    |
| BXP_4041  | 404  | No readings for location             |
| BXP_5000  | 500  | Internal server error                |
