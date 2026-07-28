# BXP Protocol Reference Node

**Open universal standard for atmospheric exposure data.**
BXP is to air quality data what MP4 is to video — a universal format any system can read, write, and exchange.

## Project overview

| Component | Location | Description |
|---|---|---|
| Reference server | `reference-server/server.py` | FastAPI node — the core of BXP |
| Database layer | `reference-server/database.py` | SQLite persistence via `bxp_data.db` |
| Python SDK | `sdk/python/bxp_sdk.py` | Sync + async client, file I/O, HRI calc |
| TypeScript SDK | `sdk/typescript/bxp-sdk.ts` | Full-feature TS/JS SDK |
| CLI | `cli/bxp_cli.py` | `bxp` command-line tool |
| MQTT bridge | `integrations/mqtt_bridge.py` | Subscribe → submit to BXP node |
| Tests | `reference-server/tests/` | pytest suite |
| Postman collection | `postman/BXP_Protocol.postman_collection.json` | Importable API collection |
| Docker | `Dockerfile`, `docker-compose.yml` | One-command node deployment |

## How to run

```bash
cd reference-server
pip install -r requirements.txt
python server.py
```

Server starts at **http://localhost:5000**

- Landing page: `/`
- Dashboard: `/dashboard`
- Global map: `/map`
- City comparison: `/compare`
- Interactive API docs: `/docs`
- Prometheus metrics: `/metrics`

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `AQICN_TOKEN` | Recommended | Free token from https://aqicn.org/api/ — enables live city data |
| `BXP_NODE_ID` | Optional | Node identifier (default: `bxp-public-node-001`) |
| `BXP_NODE_TYPE` | Optional | Node type (default: `reference`) |
| `BXP_SERVER_URL` | Optional | SDK/CLI default server (default: `http://localhost:5000`) |
| `BXP_DEVICE_TOKEN` | Optional | SDK/CLI default device token |

Set `AQICN_TOKEN` as a Replit Secret to enable live global air quality data.

## Key API endpoints

```
GET  /bxp/v2/health                      Node health & stats
GET  /bxp/v2/city/{city}                 Live city data (AQICN)
POST /bxp/v2/readings                    Submit readings (returns 201)
GET  /bxp/v2/readings                    List readings (paginated)
GET  /bxp/v2/readings/{id}               Get reading by ID
GET  /bxp/v2/readings/{id}/verify        Integrity check (§2.2)
DEL  /bxp/v2/readings/{id}              Cryptographic deletion (§9)
GET  /bxp/v2/locations/{gh}/latest       Latest reading at geohash
GET  /bxp/v2/locations/{gh}/aggregate    k≥5 privacy aggregate (§9)
GET  /bxp/v2/search                      Search by city or coordinates
POST /bxp/v2/devices/register            Register device, get token
POST /bxp/v2/community/reports           Submit community report
GET  /bxp/v2/nodes                       Federated node list
GET  /metrics                            Prometheus metrics
GET  /widget/{city}                      Embeddable iframe widget
```

## Running tests

```bash
cd reference-server
pip install pytest httpx
python -m pytest tests/ -v
```

## CLI usage

```bash
cd cli
python bxp_cli.py generate --pm25 47.2 --lat 5.6037 --lon -0.1870
python bxp_cli.py hri --pm25 67.0 --no2 31.0 --duration 8h --population sensitive
python bxp_cli.py submit --file reading.bxp.json
python bxp_cli.py batch-submit --dir ./readings/
python bxp_cli.py export reading.bxp.json --format csv
python bxp_cli.py map ./readings/ --output map.html
python bxp_cli.py server-status
python bxp_cli.py config set server http://localhost:5000
```

## Docker

```bash
cp .env.example .env   # add AQICN_TOKEN
docker-compose up -d
```

## User preferences

- Keep existing project structure and stack (FastAPI + Python)
- SQLite database at `reference-server/bxp_data.db`
- Port 5000 for the server
