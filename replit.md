# BXP — Breathe Exposure Protocol

## Project Overview

**BXP** is an open universal standard for atmospheric exposure data — the "MP4 for air quality."
It defines a complete protocol stack: file format, REST API, health risk index (BXP_HRI),
privacy framework, and federated node architecture. Apache 2.0. Free forever.

- **GitHub:** https://github.com/bxpprotocol/bxp-spec
- **Spec DOI:** https://doi.org/10.5281/zenodo.18906812
- **Implementation DOI:** https://doi.org/10.5281/zenodo.18907003
- **ORCID:** https://orcid.org/0009-0001-4856-4986

## Running the Server

```bash
cd reference-server
python server.py
```

Server runs at `http://0.0.0.0:5000` (port 5000). The Replit workflow "Start application" handles this automatically.

## Environment Variables

| Variable | Required | Purpose |
|---|---|---|
| `AQICN_TOKEN` | Optional | Live city air quality data (get free at https://aqicn.org/api/). Without it, only submitted readings are available. |
| `BXP_NODE_ID` | Optional | Overrides default node ID (`bxp-public-node-001`) |
| `BXP_NODE_TYPE` | Optional | Overrides node type (`reference`) |
| `SESSION_SECRET` | Optional | Session secret for secure cookies |

## Repository Structure

```
bxp-protocol/
├── reference-server/
│   ├── server.py           FastAPI reference node v2.1
│   ├── database.py         SQLite helpers (readings, devices, reports, nodes)
│   ├── requirements.txt    fastapi, uvicorn, pydantic, httpx
│   └── tests/
│       └── test_server.py  Pytest test suite
├── sdk/
│   ├── python/
│   │   ├── bxp_sdk.py      Python SDK v2.1 (sync + async, offline queue)
│   │   └── pyproject.toml  pip-installable package config
│   └── typescript/
│       └── bxp-sdk.ts      TypeScript/Node.js SDK
├── cli/
│   └── bxp_cli.py          CLI tool v2.1 (generate, submit, export, map, config)
├── spec/
│   └── bxp-v2.0.md         Full protocol specification
├── docs/
│   ├── index.html          Professional landing page (GitHub Pages)
│   └── validator.html      BXP JSON validator & playground
├── datasets/
│   └── sample_readings.bxp.json  10 global city readings
├── examples/
│   ├── example_generate.py
│   └── example_read.py
├── integrations/
│   └── mqtt_bridge.py      MQTT → BXP bridge
├── postman/
│   └── BXP_Protocol.postman_collection.json
├── .github/
│   └── workflows/ci.yml    GitHub Actions CI (Python 3.10/3.11/3.12)
├── Dockerfile
└── docker-compose.yml
```

## Key API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/` | Landing page |
| GET | `/bxp/v2/health` | Node health + uptime |
| GET | `/bxp/v2/city/{city}` | Live BXP data for a city (AQICN) |
| GET | `/bxp/v2/readings` | List readings (filter by geohash, time, agent) |
| POST | `/bxp/v2/readings` | Submit readings (returns 201) |
| DELETE | `/bxp/v2/readings/{id}` | Delete with cryptographic proof |
| GET | `/bxp/v2/readings/{id}/verify` | Integrity check |
| GET | `/bxp/v2/locations/{geohash}/aggregate` | k≥5 privacy-safe aggregate |
| GET | `/bxp/v2/search` | Search by city name or coordinates |
| POST | `/bxp/v2/devices/register` | Register device, receive token |
| POST | `/bxp/v2/community/reports` | Submit community air quality report |
| GET | `/bxp/v2/nodes` | Federated node list |
| GET | `/metrics` | Prometheus metrics |
| GET | `/widget/{city}` | Embeddable iframe widget |
| GET | `/dashboard` | Global dashboard (search) |
| GET | `/dashboard/{city}` | City dashboard (map + chart + readings) |
| GET | `/map` | Global map view |
| GET | `/compare` | City comparison tool |
| GET | `/docs` | Swagger UI |

## GitHub Pages (docs/)

The `docs/` folder is served via GitHub Pages at https://bxpprotocol.github.io/
- `docs/index.html` — professional protocol landing page
- `docs/validator.html` — BXP JSON validator & playground

## User Preferences

- Keep the project open source (Apache 2.0) — never commit secrets or API keys
- AQICN_TOKEN must stay in environment variables only, never in code
- Maintain existing project structure; do not migrate database or restructure unnecessarily
- The server listens on port 5000 (Replit default)
