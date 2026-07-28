# BXP Evidence Index
## Claim-to-Evidence Mapping

Every major claim in the BXP evidence package is mapped here to the actual evidence that supports it.

---

## Format

| Claim | Evidence | File | Status |
|-------|---------|------|--------|
| Description of claim | What supports it | Where to find it | Honest assessment |

---

## Protocol Existence and Design

| Claim | Evidence | File | Status |
|-------|---------|------|--------|
| BXP v2.0 protocol specification exists | 1,300-line formal specification | `SPEC.md` | ✅ Complete |
| Protocol was first conceived February 15, 2026 | Statement in specification Origin & Authorship section | `SPEC.md`, line 1288 | ✅ Documented |
| BXP v1.0 established user-owned data, offline-first, SHA-256 verification | Listed in CHANGELOG v1.0 section | `CHANGELOG.md` | ✅ Documented |
| Protocol published to Zenodo with permanent DOI | Zenodo record with DOI 10.5281/zenodo.18906812 | https://doi.org/10.5281/zenodo.18906812 | ✅ Published |
| Specification covers 31 atmospheric agents | Agent schema section of SPEC.md; Appendix A | `SPEC.md §6, Appendix A` | ✅ Complete |
| Protocol specifies 5-stage data pipeline | SPEC.md §7 | `SPEC.md §7` | ✅ Complete |
| Protocol specifies 20+ REST API endpoints | SPEC.md §8 and reference server | `SPEC.md §8`, `reference-server/server.py` | ✅ Complete |
| Agent thresholds aligned with WHO 2021 guidelines | Threshold values in spec match WHO AQG 2021 | `SPEC.md §6`, cited in References | ✅ Verifiable |
| Binary file format specified with 32-byte header | SPEC.md §5.2 | `SPEC.md §5.2` | 📄 Specified, not implemented |
| BXP volume file system architecture defined | SPEC.md §4 | `SPEC.md §4` | 📄 Specified, not physically implemented |

---

## Reference Implementation

| Claim | Evidence | File | Status |
|-------|---------|------|--------|
| Working reference server exists | ~1,877-line FastAPI server | `reference-server/server.py` | ✅ Working |
| Server accepts POST /bxp/v2/readings and returns 201 | Server code + API docs | `reference-server/server.py:581` | ✅ Implemented |
| Server uses SQLite for persistence | SQLite database file and database.py | `reference-server/database.py` | ✅ Implemented |
| Device token authentication implemented | Auth validation in server | `reference-server/server.py` | ✅ Implemented |
| Rate limiting implemented (per-IP sliding window) | RateLimiter class in server | `reference-server/server.py:158` | ✅ Implemented |
| Privacy controls implemented (geohash floor, k≥5) | Privacy logic in submit_readings + aggregate endpoint | `reference-server/server.py` | ✅ Implemented |
| Cryptographic deletion with proof implemented | DELETE endpoint | `reference-server/server.py:690` | ✅ Implemented |
| Integrity verification endpoint exists | GET /readings/{id}/verify | `reference-server/server.py:723` | ✅ Implemented |
| Community reports implemented | POST/GET /community/reports | `reference-server/server.py` | ✅ Implemented |
| Device registration implemented | POST/GET /devices/register | `reference-server/server.py` | ✅ Implemented |
| Interactive dashboard with map and charts | Dashboard route at / | `reference-server/server.py` | ✅ Implemented |
| Prometheus metrics endpoint | GET /metrics | `reference-server/server.py` | ✅ Implemented |
| Embeddable widget | GET /widget/{city} | `reference-server/server.py` | ✅ Implemented |
| Server can be started with one command | `python server.py` after `pip install -r requirements.txt` | `reference-server/requirements.txt` | ✅ Verified |
| Implementation published to Zenodo with DOI | DOI 10.5281/zenodo.18907003 | https://doi.org/10.5281/zenodo.18907003 | ✅ Published |

---

## BXP_HRI (Health Risk Index)

| Claim | Evidence | File | Status |
|-------|---------|------|--------|
| BXP_HRI is a composite index incorporating all agents | Formula in SPEC.md §13 and implemented in SDK | `SPEC.md §13`, `sdk/python/bxp_sdk.py:145` | ✅ Implemented |
| Weights derived from WHO DALY burden data | Stated in spec with basis; WHO reference cited | `SPEC.md §13.2` | ✅ Justified; not independently validated |
| Duration factors (1h/8h/24h) applied | Implemented in SDK and server | `bxp_sdk.py`, `server.py` | ✅ Implemented |
| Vulnerability factors (general/sensitive) applied | Implemented in SDK and server | `bxp_sdk.py`, `server.py` | ✅ Implemented |
| Six risk levels (CLEAN through HAZARDOUS) | Defined in spec and implemented in SDK | `SPEC.md §7 Stage 4`, `bxp_sdk.py:78` | ✅ Implemented |
| BXP_HRI has not been clinically validated | Acknowledged in specification limitations | Research report §5.2 | ⚠️ Limitation acknowledged |

---

## Python SDK

| Claim | Evidence | File | Status |
|-------|---------|------|--------|
| Python SDK exists | ~895-line bxp_sdk.py | `sdk/python/bxp_sdk.py` | ✅ Complete |
| write_bxp() creates valid .bxp.json files with SHA-256 hash | Implemented and used in examples | `bxp_sdk.py:270` | ✅ Implemented |
| read_bxp() verifies integrity on read | Implemented | `bxp_sdk.py:381` | ✅ Implemented |
| validate_bxp() checks against spec | Implemented with all required field checks | `bxp_sdk.py:409` | ✅ Implemented |
| Synchronous BXPClient implemented | Implemented | `bxp_sdk.py` | ✅ Implemented |
| Asynchronous AsyncBXPClient implemented | Implemented using httpx | `bxp_sdk.py` | ✅ Implemented |
| OfflineQueue with disk persistence implemented | Implemented | `bxp_sdk.py:492` | ✅ Implemented |
| pip packaging files present | pyproject.toml and setup.py exist | `sdk/python/pyproject.toml`, `sdk/python/setup.py` | ✅ Present |

---

## TypeScript SDK

| Claim | Evidence | File | Status |
|-------|---------|------|--------|
| TypeScript SDK exists | bxp-sdk.ts with package.json | `sdk/typescript/bxp-sdk.ts` | ✅ Present |

---

## CLI Tool

| Claim | Evidence | File | Status |
|-------|---------|------|--------|
| CLI tool exists and supports multiple commands | 740+-line bxp_cli.py | `cli/bxp_cli.py` | ✅ Complete |
| generate, read, validate commands implemented | Source code | `cli/bxp_cli.py:129, 193, 254` | ✅ Implemented |
| submit and batch-submit implemented | Source code | `cli/bxp_cli.py:317, 357` | ✅ Implemented |
| export (CSV/GeoJSON) implemented | Source code | `cli/bxp_cli.py` | ✅ Implemented |
| map (HTML generation) implemented | Source code | `cli/bxp_cli.py` | ✅ Implemented |
| BXP_SERVER_URL and BXP_DEVICE_TOKEN env vars supported | Source code | `cli/bxp_cli.py:64, 75` | ✅ Implemented |
| Config file (~/.bxp/config.json) implemented | Source code | `cli/bxp_cli.py:45` | ✅ Implemented |

---

## Sample Dataset

| Claim | Evidence | File | Status |
|-------|---------|------|--------|
| Sample dataset contains 10 global city readings | JSON file with 10 readings | `datasets/sample_readings.bxp.json` | ✅ Present |
| Dataset covers 6 continents | Accra, Lagos (Africa), Delhi, Beijing, Jakarta (Asia), London (Europe), São Paulo (South America), New York (North America), Nairobi (Africa), Cairo (Africa) | `datasets/sample_readings.bxp.json` | ✅ Verifiable |
| All readings use BXP v2.0 schema | bxpVersion: "2.0" in all records | `datasets/sample_readings.bxp.json` | ✅ Verifiable |

---

## Ecosystem and Infrastructure

| Claim | Evidence | File | Status |
|-------|---------|------|--------|
| MQTT bridge exists | mqtt_bridge.py | `integrations/mqtt_bridge.py` | ✅ Present |
| Docker deployment configured | Dockerfile and docker-compose.yml | `Dockerfile`, `docker-compose.yml` | ✅ Present |
| Postman collection exists | JSON collection file | `postman/BXP_Protocol.postman_collection.json` | ✅ Present |
| GitHub Actions CI configured | CI workflow YAML | `.github/workflows/ci.yml` | ✅ Present |
| CONTRIBUTING.md exists | Contribution guidelines | `CONTRIBUTING.md` | ✅ Present |

---

## Claimed But Not Yet Implemented / Verifiable

| Claim | Status | Notes |
|-------|--------|-------|
| Binary .bxp file format implemented | ❌ Not implemented | Specified in SPEC.md §5.2; no encoder/decoder code exists |
| Federated node synchronisation | ❌ Not implemented | /nodes endpoint exists; P2P sync is not built |
| BXP Foundation governance body | ❌ Does not exist | Proposed in SPEC.md §12.1 |
| Compatibility with GDPR/CCPA/HIPAA | ⚠️ Designed, not audited | Privacy architecture is designed for compliance; no formal legal review |
| HL7 FHIR R4 mapping | ⚠️ Listed in compatibility matrix; not documented in detail |  |
| External adoption by any organisation | ❌ None yet | Reference implementation is the only working implementation |
| BXP_HRI clinically validated | ❌ Not validated | Weights are WHO-derived; no epidemiological review conducted |
| Arduino/ESP32 SDKs | ❌ Not built | Listed in CHANGELOG §Upcoming |

---

*Copyright 2026 Elvarin — Apache 2.0*
