# BXP — Breathe Exposure Protocol

**The open universal standard for atmospheric exposure data.**

BXP is to air quality data what MP4 is to video — a universal file format
and protocol that any system can read, write, and exchange.
Owned by nobody. Usable by everyone. Free forever.

[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![BXP Version](https://img.shields.io/badge/BXP-v2.0-green.svg)](spec/bxp-v2.0.md)
[![GitHub](https://img.shields.io/badge/GitHub-bxpprotocol-black.svg)](https://github.com/bxpprotocol/bxp-spec)

---

## What is BXP?

Air pollution causes **7 million premature deaths annually**.
The sensors exist. The data infrastructure does not.

BXP defines a complete open standard for atmospheric exposure data:

- **`.bxp` file format** — universal JSON-based data container
- **BXP_HRI** — composite Health Risk Index (WHO-derived, 0-100 scale)
- **REST API** — standard endpoints any system can implement
- **31 atmospheric agents** — PM2.5, NO2, ozone, benzene, mold, and more
- **Federated network** — decentralized, no single owner, data sovereignty preserved
- **Privacy framework** — personal exposure data protected by design

---

## Repository Structure

```
bxp-protocol/
├── spec/
│   └── bxp-v2.0.md              Protocol specification
├── reference-server/
│   ├── server.py                 FastAPI reference server
│   └── requirements.txt
├── cli/
│   └── bxp_cli.py               Command line tool
├── sdk/
│   └── python/
│       └── bxp_sdk.py           Python SDK
├── datasets/
│   └── sample_readings.bxp.json 10 Accra readings
├── examples/
│   ├── example_generate.py      Generate .bxp files
│   └── example_read.py          Read and analyze .bxp files
├── docs/
│   ├── protocol_overview.md
│   ├── api_documentation.md
│   └── developer_guide.md
├── README.md
└── LICENSE
```

---

## Quick Start

### Install dependencies

```bash
cd reference-server
pip install -r requirements.txt
```

### Start the server

```bash
python server.py
```

Server starts at **http://localhost:8000**
Interactive API docs: **http://localhost:8000/docs**

The server loads 10 global city readings automatically.

---

## Using the CLI

```bash
# Generate a .bxp file
python cli/bxp_cli.py generate --pm25 47.2 --lat 5.6037 --lon -0.1870

# Generate with full details
python cli/bxp_cli.py generate \
    --pm25 47.2 --pm10 62.1 --no2 18.3 --o3 12.0 \
    --temp 29 --rh 78 \
    --lat 5.6037 --lon -0.1870 \
    --location "Accra Central"

# Read a .bxp file
python cli/bxp_cli.py read reading_20260307_100000.bxp.json

# Validate a .bxp file
python cli/bxp_cli.py validate reading_20260307_100000.bxp.json

# Calculate BXP_HRI
python cli/bxp_cli.py hri --pm25 67.0 --no2 31.0

# Check server status
python cli/bxp_cli.py server-status --server http://localhost:8000
```

---

## Example API Calls

```bash
# Submit a reading
curl -X POST http://localhost:8000/bxp/v2/readings \
  -H "Content-Type: application/json" \
  -d '{
    "readings": [{
      "latitude": 5.6037,
      "longitude": -0.1870,
      "agents": [
        {"agentId": "PM2_5", "value": 47.2, "unit": "ug/m3"},
        {"agentId": "NO2",   "value": 18.3, "unit": "ppb"}
      ]
    }]
  }'

# Get latest reading for Accra
curl http://localhost:8000/bxp/v2/locations/s1v0g/latest

# Get all readings
curl http://localhost:8000/bxp/v2/readings

# Calculate HRI
curl -X POST "http://localhost:8000/bxp/v2/hri/calculate" \
  -H "Content-Type: application/json" \
  -d '[{"agentId": "PM2_5", "value": 67.0, "unit": "ug/m3"}]'

# Server health
curl http://localhost:8000/bxp/v2/health
```

---

## Example Output

### CLI generate

```
  BXP file generated: reading_20260307_100000.bxp.json
────────────────────────────────────────────────────
  Geohash:    s1v0gx4
  Location:   5.6037, -0.1870
  Agents:     2
    PM2_5: 47.2 ug/m3  ↑ EXCEEDS WHO (15)
    NO2:   18.3 ppb     ✓ within WHO (25)

────────────────────────────────────────────────────
  BXP Health Risk Index  61.2  [HIGH]
  Wear N95 outdoors. Close windows.
────────────────────────────────────────────────────
```

### Sample .bxp.json file

```json
{
  "bxpVersion": "2.0",
  "deviceUuid": "550e8400-e29b-41d4-a716-446655440000",
  "geohash": "s1v0gx4",
  "latitude": 5.6037,
  "longitude": -0.1870,
  "timestampUs": 1741342800000000,
  "durationS": 60,
  "indoorOutdoor": "outdoor",
  "agents": [
    { "agentId": "PM2_5", "value": 47.2, "unit": "ug/m3" },
    { "agentId": "NO2",   "value": 18.3, "unit": "ppb"   }
  ],
  "quality": {
    "flag": "UNVALIDATED",
    "confidence": 0.8,
    "qcMethod": "client-generated"
  },
  "bxpHri": 61.2,
  "bxpHriLevel": "HIGH",
  "bxpHriColor": "#CC0000",
  "payloadHash": "sha256:a3f2b1..."
}
```

---

## Python SDK

```python
from bxp_sdk import write_bxp, read_bxp, calculate_risk, BXPClient

# Calculate risk
risk = calculate_risk(pm25=67.0, no2=31.0)
print(risk["score"])   # 72.4
print(risk["level"])   # HIGH

# Write a file
write_bxp("reading.bxp.json", {
    "latitude": 5.6037, "longitude": -0.1870,
    "pm25": 47.2, "no2": 18.3
})

# Submit to server
client = BXPClient("http://localhost:8000")
result = client.submit(latitude=5.6037, longitude=-0.1870, pm25=47.2)
print(result["bxpHri"])   # 61.2
```

---

## Run the Examples

```bash
# Generate sample files
python examples/example_generate.py

# Read and analyze
python examples/example_read.py
```

---

## License

Apache 2.0 — Free to use, implement, modify, and distribute.
No royalties. No restrictions. No gatekeepers.

---

## Links

- Specification: [spec/bxp-v2.0.md](spec/bxp-v2.0.md)
- API Docs: [docs/api_documentation.md](docs/api_documentation.md)
- Developer Guide: [docs/developer_guide.md](docs/developer_guide.md)
- GitHub: https://github.com/bxpprotocol/bxp-spec
- Website: https://bxpprotocol.github.io
- Contact: bxpprotocol@proton.me

---

*The air is public. The data should be too.*
