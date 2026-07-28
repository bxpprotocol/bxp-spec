# BXP — Breathe Exposure Protocol

Open standard for atmospheric exposure data. Like HTTP for the web — any device writes it, any software reads it, nobody owns it.

**License:** Apache 2.0  
**Spec DOI:** https://doi.org/10.5281/zenodo.18906812  
**GitHub:** https://github.com/bxpprotocol/bxp-spec

---

## How to Run

```bash
cd reference-server
python server.py
```

Server starts on **port 5000**.  
- Homepage: `/`  
- Dashboard: `/dashboard` or `/dashboard/{city}`  
- API docs: `/docs`  
- Health: `/bxp/v2/health`

The workflow **Start application** is configured to run automatically.

---

## Project Structure

```
bxp-protocol/
├── spec/
│   └── bxp-v2.0.md              Protocol specification
├── reference-server/
│   ├── server.py                 FastAPI reference server (port 5000)
│   └── requirements.txt
├── cli/
│   └── bxp_cli.py               Command line tool
├── sdk/
│   └── python/
│       └── bxp_sdk.py           Python SDK
├── datasets/
│   └── sample_readings.bxp.json Sample data
├── examples/
│   ├── example_generate.py
│   └── example_read.py
└── docs/
    ├── protocol_overview.md
    ├── api_documentation.md
    └── developer_guide.md
```

---

## Environment Variables

| Key | Required | Description |
|-----|----------|-------------|
| `AQICN_TOKEN` | Yes | AQICN API token for real-time city data. Get one at https://aqicn.org/api/ |

---

## REST API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/bxp/v2/health` | Node health + stats |
| GET | `/bxp/v2/readings` | List readings (query: geohash, from, to, agent, quality, limit) |
| POST | `/bxp/v2/readings` | Submit new readings (BXP format) |
| GET | `/bxp/v2/readings/{id}` | Get reading by ID |
| GET | `/bxp/v2/locations/{geohash}/latest` | Latest reading for a location |
| GET | `/bxp/v2/locations/{geohash}/history` | History for a location |
| GET | `/dashboard` | Live global dashboard UI |
| GET | `/dashboard/{city}` | City-specific dashboard |

---

## User Preferences

- Keep the existing project structure — do not restructure or migrate
- Maintain Apache 2.0 open-source ethos throughout
