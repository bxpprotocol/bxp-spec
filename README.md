<p align="center">
  <img src="assets/banner.svg" alt="BXP — Breathe Exposure Protocol" width="100%">
</p>

<p align="center">
  <a href="LICENSE"><img alt="License" src="https://img.shields.io/badge/license-Apache%202.0-blue.svg"></a>
  <a href="SPEC.md"><img alt="BXP Version" src="https://img.shields.io/badge/BXP-v2.0-2ea44f.svg"></a>
  <a href="https://doi.org/10.5281/zenodo.18906812"><img alt="Spec DOI" src="https://zenodo.org/badge/DOI/10.5281/zenodo.18906812.svg"></a>
  <a href="https://github.com/bxpprotocol/bxp-spec/actions"><img alt="CI" src="https://github.com/bxpprotocol/bxp-spec/actions/workflows/ci.yml/badge.svg"></a>
  <a href="https://github.com/bxpprotocol/bxp-spec"><img alt="GitHub" src="https://img.shields.io/badge/GitHub-bxpprotocol-black.svg"></a>
  <a href="https://pypi.org/project/bxp-sdk/"><img alt="PyPI" src="https://img.shields.io/badge/PyPI-bxp--sdk-3775A9.svg?logo=pypi&logoColor=white"></a>
  <a href="https://www.npmjs.com/package/@bxp/sdk"><img alt="npm" src="https://img.shields.io/badge/npm-@bxp%2Fsdk-CB3837.svg?logo=npm&logoColor=white"></a>
  <a href="https://discord.gg/bxp"><img alt="Discord" src="https://img.shields.io/badge/Discord-BXP%20Community-5865F2.svg?logo=discord&logoColor=white"></a>
  <a href="GOVERNANCE.md"><img alt="Governance" src="https://img.shields.io/badge/Governance-Transparent-8A2BE2.svg"></a>
</p>

<p align="center">
  <b>BXP is to air quality data what HTTP is to the web</b> — a protocol, not a platform.<br>
  A common data language that any sensor, any agency, and any application can speak.<br>
  Owned by nobody. Usable by everyone. Free forever.
</p>

<p align="center">
  <a href="https://bxpprotocol.github.io/bxp-spec/validator.html"><img alt="Try Validator" src="https://img.shields.io/badge/🔍_Live_Validator-Try_It_Now-FF6B35.svg?style=for-the-badge"></a>
  <a href="#quick-start"><img alt="Quick Start" src="https://img.shields.io/badge/🚀_Quick_Start-30_Seconds-00D9AA.svg?style=for-the-badge"></a>
  <a href="https://github.com/bxpprotocol/bxp-spec/discussions"><img alt="Discussions" src="https://img.shields.io/badge/💬_Discussions-Join_Us-6F42C1.svg?style=for-the-badge"></a>
</p>

<p align="center">
  <a href="#the-problem">The Problem</a> ·
  <a href="#the-solution">The Solution</a> ·
  <a href="#quick-start">Quick Start</a> ·
  <a href="#architecture">Architecture</a> ·
  <a href="#bxp_hri--health-risk-index">Health Risk Index</a> ·
  <a href="#current-status">Status</a> ·
  <a href="#roadmap">Roadmap</a> ·
  <a href="#documentation">Docs</a> ·
  <a href="#contributing">Contributing</a>
</p>

---

## 🎯 The Problem

Air pollution causes **7 million premature deaths annually** — more than HIV, malaria, and tuberculosis combined (WHO, 2021).

The sensors to measure it exist. The data infrastructure does not.

Every sensor manufacturer, government agency, and research network uses incompatible data formats. A sensor in Accra cannot feed a dashboard in Nairobi. A citizen reading in Delhi cannot contribute to a government pollution map. A researcher in London cannot query a database in Lagos using a single standard format.

**The barrier is not hardware. It is data fragmentation.**

## ✨ The Solution

| | |
|---|---|
| 📄 **`.bxp.json`** | A universal file format for atmospheric exposure data — one schema for any source, any location, any pollutant |
| 🩺 **BXP-HRI (experimental)** | A composite Health Risk Index (0–100) derived from all available agents, weighted by WHO disease-burden data — **not clinically validated** |
| 🌐 **REST API** | A standard set of endpoints any BXP node must implement, so any client can query any node |
| 🧪 **30+ atmospheric agents** | PM1, PM2.5, PM10, NO₂, O₃, CO, SO₂, benzene, formaldehyde, mold spores, heavy metals, and more — see [Appendix A](SPEC.md#appendix-a--complete-agent-reference) |
| 🔒 **Privacy framework** | SHA-256 hashed identifiers, geohash precision floors, k-anonymisation, cryptographic deletion |
| 🕸️ **Federated architecture** | No central owner — any organisation can run a BXP node on their own infrastructure |

## 📦 Repository Structure

```
bxp-protocol/
├── SPEC.md                          Protocol specification v2.0
├── CHANGELOG.md                     Development history
├── CONTRIBUTING.md                  Contribution guide
├── GOVERNANCE.md                    Project governance & transparency
├── reference-server/
│   ├── server.py                    FastAPI reference node v2.1
│   ├── database.py                  SQLite persistence layer
│   ├── requirements.txt             Python dependencies
│   └── tests/                       Pytest suite
├── sdk/
│   ├── python/bxp_sdk.py            Python SDK v2.1
│   ├── python/bxp_binary.py         Native binary .bxp codec
│   └── typescript/
│       ├── bxp-sdk.ts               TypeScript SDK
│       └── bxp-binary.ts            Native binary .bxp codec (TS)
├── conformance/                     Cross-implementation golden test vectors
│   ├── vectors/                     17 golden .bxp files (valid + malformed)
│   ├── generate_vectors.py
│   ├── verify_python.py
│   └── verify_typescript.mjs
├── cli/bxp_cli.py                   Command-line tool v2.1
├── integrations/
│   ├── mqtt_bridge.py               MQTT → BXP bridge
│   └── openaq_import.py             OpenAQ v3 API → BXP importer
├── datasets/sample_readings.bxp.json  10 global city readings
├── docs/
│   ├── api_documentation.md
│   ├── developer_guide.md
│   ├── protocol_overview.md
│   ├── index.html                   Landing page (GitHub Pages)
│   └── validator.html               BXP JSON validator & playground
├── postman/BXP_Protocol.postman_collection.json
├── assets/                          README/site imagery
├── Dockerfile
└── docker-compose.yml
```

## 🚀 Quick Start

<details open>
<summary><b>🐳 Docker (Recommended)</b></summary>

```bash
# Clone and start in one command
git clone https://github.com/bxpprotocol/bxp-spec.git
cd bxp-spec
docker compose up
```

**Open:** `http://localhost:5000` — Dashboard | `http://localhost:5000/docs` — Interactive API | `http://localhost:5000/health` — Health check

</details>

<details>
<summary><b>🐍 Python (pip)</b></summary>

```bash
# Install SDK
pip install bxp-sdk  # coming in v2.1

# Or run from source
pip install -r reference-server/requirements.txt
cd reference-server && python server.py
```

</details>

<details>
<summary><b>📦 Node.js (npm)</b></summary>

```bash
# Install SDK
npm install @bxp/sdk  # coming in v2.1
```

</details>

### Using the Python SDK

```python
from bxp_sdk import write_bxp, read_bxp, calculate_risk, BXPClient

# Calculate health risk from sensor values
risk = calculate_risk(pm25=67.0, no2=31.0, duration="24h", population="sensitive")
print(risk["score"])   # 89.6
print(risk["level"])   # VERY_HIGH

# Write a .bxp.json file
record = write_bxp("accra.bxp.json", {
    "latitude": 5.6037, "longitude": -0.1870,
    "pm25": 47.2, "no2": 18.3, "temp": 29.0,
    "source": "native"  # NEW in v2.0: source classification
})
print(record["bxpHri"])       # 61.2
print(record["bxpHriLevel"])  # HIGH

# Read and verify
data = read_bxp("accra.bxp.json")
print(data["_integrityOk"])   # True

# Submit to a BXP node
client = BXPClient("http://localhost:5000")
result = client.submit(latitude=5.6037, longitude=-0.1870, pm25=47.2)
```

### Using the CLI

```bash
# Generate a .bxp.json file
python cli/bxp_cli.py generate --pm25 47.2 --no2 18.3 --lat 5.6037 --lon -0.1870

# Validate against BXP v2.0 spec
python cli/bxp_cli.py validate reading.bxp.json

# Calculate health risk
python cli/bxp_cli.py hri --pm25 67.0 --no2 31.0 --duration 8h --population sensitive

# Submit to a node
python cli/bxp_cli.py submit --server http://localhost:5000 --file reading.bxp.json

# Batch submit a directory of readings
python cli/bxp_cli.py batch-submit --dir ./sensor_data/

# Export as CSV
python cli/bxp_cli.py export reading.bxp.json --format csv

# Generate HTML map
python cli/bxp_cli.py map ./readings/ --output map.html
```

## 🎮 Live Demo

| Tool | Link | Description |
|------|------|-------------|
| **JSON Validator** | [bxpprotocol.github.io/bxp-spec/validator.html](https://bxpprotocol.github.io/bxp-spec/validator.html) | Paste JSON → instant validation + HRI calculation |
| **API Docs (Swagger)** | `http://localhost:5000/docs` | Interactive OpenAPI 3.0 docs (run server first) |
| **Dashboard** | `http://localhost:5000/` | Live city data, maps, health advisories |
| **Postman Collection** | `postman/BXP_Protocol.postman_collection.json` | Ready-to-use API requests |

> 💡 **No install needed** — try the validator in your browser right now.

## API Examples

```bash
# Submit a reading
curl -X POST http://localhost:5000/bxp/v2/readings \
  -H "Content-Type: application/json" \
  -d '{"readings":[{"latitude":5.6037,"longitude":-0.1870,
       "agents":[{"agentId":"PM2_5","value":47.2,"unit":"ug/m3"}]}]}'

# Get latest for a location
curl http://localhost:5000/bxp/v2/locations/s1v0g/latest

# Get live city data
curl http://localhost:5000/bxp/v2/city/accra

# Server health
curl http://localhost:5000/bxp/v2/health
```

## Architecture

BXP uses a five-stage data pipeline:

```mermaid
flowchart LR
    A[📍 LOCATE] --> B[🔎 DETECT] --> C[🧠 INTERPRET] --> D[🛡️ PROTECT] --> E[📊 REPORT]
```

| Stage | What Happens |
|-------|-------------|
| LOCATE | Geographic context attached (geohash, coordinates) |
| DETECT | Source classified (Tier 1 phone → Tier 3 reference instrument) |
| INTERPRET | QC applied, units normalised, quality flag assigned |
| PROTECT | BXP-HRI (experimental) calculated, risk level and advice generated |
| REPORT | Stored, queryable, privacy-safe |

```mermaid
flowchart TB
    subgraph Sources
        S1[Phone sensor]
        S2[Fixed IoT sensor]
        S3[Reference instrument]
        S4[Community report]
    end
    Sources --> N1[(BXP Node A)]
    Sources --> N2[(BXP Node B)]
    N1 <-->|federated sync – planned| N2
    N1 --> C1[Dashboard / App]
    N2 --> C2[Research query]
```

No node owns the network — any organisation runs its own, and clients can query across nodes using the same schema and API.

## BXP-HRI (experimental) — Health Risk Index

A composite 0–100 score incorporating all available agents simultaneously, weighted by WHO disability-adjusted life year burden data. **Not clinically or epidemiologically validated — do not use for medical decisions.**

| Score | Level | Guidance |
|-------|-------|----------|
| 0–20 | 🟢 CLEAN | No restrictions |
| 21–40 | 🟡 MODERATE | Sensitive groups: limit exertion |
| 41–60 | 🟠 ELEVATED | Reduce outdoor exertion |
| 61–75 | 🔴 HIGH | N95 outdoors, close windows |
| 76–90 | 🟣 VERY HIGH | Avoid outdoor activity |
| 91–100 | ⚫ HAZARDOUS | Health emergency |

## Current Status

| Component | Status |
|-----------|--------|
| BXP v2.0 specification | ✅ Complete, with an explicit conformance model (§3.7, §15) |
| Reference server v2.1 | ✅ Core reading/query endpoints implemented, including `/nearby` and `/sync` |
| Python SDK v2.1 | ✅ Complete, including native binary format |
| TypeScript SDK | ✅ Complete, including native binary format (new) |
| CLI tool v2.1 | ✅ Complete |
| MQTT bridge | ✅ Complete |
| OpenAQ importer | ✅ Complete — converts OpenAQ v3 data into valid BXP records |
| Sample dataset | ✅ Complete |
| Binary `.bxp` format | ✅ Implemented in Python and TypeScript; verified byte-for-byte interoperable via `conformance/` |
| Conformance test suite | ✅ 17 golden vectors, Python + TypeScript both passing |
| Embedded (C/Arduino/ESP32) | 🗓️ Planned, not yet implemented |
| Federated node sync (`/sync`) | ✅ Implemented (§7 Stage 7) — cursor-based pull replication, deletions propagate as tombstones; trust/reputation/dedup between nodes still unspecified |
| Nearby-observation query (`/nearby`) | ✅ Implemented (§7 Stage 6, §8.2.1) — relevance-ranked by distance, freshness, quality |

## Roadmap

**Near-term**
- Embedded C reference codec + ESP32/Arduino example, tested against the same conformance vectors as Python/TypeScript
- PurpleAir (or similar low-cost-network API) importer, following the same trust-preserving pattern as `openaq_import.py`

**v2.1 (planned)**
- Python SDK pip package publication
- JavaScript/TypeScript npm package
- Arduino SDK
- ESP32 SDK
- BXP-STREAM real-time extension

**v3.0 (planned, 2027)**
- Waterborne contamination extension
- Soil contamination extension
- IoT mesh networking protocol
- BXP-HEALTH (HL7 FHIR R4 full mapping)

## Limitations

BXP is an independent research project at prototype stage:
- Federation (`/sync`) is pull-only replication; node trust/reputation, dedup
  policy for readings arriving via multiple paths, and conflict resolution
  are explicitly out of scope for now (SPEC.md §7 Stage 7) — a caller
  replicating from several peers must handle its own dedup (e.g. by
  `readingId`)
- `/sync`'s "Node Token" auth (SPEC.md §8.2) is a shared-secret placeholder
  (`BXP_NODE_SYNC_TOKEN` env var) — real node identity/trust is deferred to
  a future RFC, same as encryption in the binary `.bxp` format
- `/nearby`'s relevance ranking (distance + freshness + quality) is an
  implementation detail, not a frozen formula — SPEC.md §7 Stage 6
  intentionally leaves this open so heuristics can improve without
  breaking the API shape
- No embedded (C/Arduino/ESP32) implementation exists yet
- No third-party has independently implemented the protocol
- BXP_HRI has not been clinically or epidemiologically validated
- The reference server is a prototype — not load-tested or security-audited in production
- The OpenAQ importer's live HTTP path has not been exercised against the real
  api.openaq.org (built and tested against a realistic offline fixture only,
  due to this development environment having no outbound network access) —
  confirm against the live API before relying on it in production

## Documentation

| Document | Location |
|----------|----------|
| Protocol specification | [`SPEC.md`](SPEC.md) |
| API reference | [`docs/api_documentation.md`](docs/api_documentation.md) |
| Developer guide | [`docs/developer_guide.md`](docs/developer_guide.md) |
| Protocol overview | [`docs/protocol_overview.md`](docs/protocol_overview.md) |
| Changelog | [`CHANGELOG.md`](CHANGELOG.md) |

## Contributing

BXP is open source under Apache 2.0. Contributions welcome.

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the RFC process. All specification changes require a 30-day public comment period via GitHub Issues.

GitHub: https://github.com/bxpprotocol/bxp-spec

## License

Apache 2.0 — Free to use, implement, modify, and distribute. No royalties. No restrictions. No gatekeepers.

## Citation

**Specification DOI:** https://doi.org/10.5281/zenodo.18906812
**Implementation DOI:** https://doi.org/10.5281/zenodo.18907003
**ORCID:** https://orcid.org/0009-0001-4856-4986

---

<p align="center"><i>The air is public. The data should be too.</i></p>
