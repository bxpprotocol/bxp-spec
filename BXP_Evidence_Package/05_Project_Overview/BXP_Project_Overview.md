# BXP Project Overview
## What is the Breathe Exposure Protocol?

**Author:** Elvarin  
**Version:** BXP v2.0  
**Date:** 2026  
**License:** Apache 2.0

---

## What is BXP?

BXP (Breathe Exposure Protocol) is an open data standard — a universal file format and protocol for recording, storing, and transmitting atmospheric exposure data. Think of it as a common language for air quality information.

Just as MP4 allows any video player to play any video file, and PDF allows any document reader to display any document, BXP allows any application to read any air quality measurement, regardless of what sensor recorded it, where it was recorded, or what system submitted it.

BXP is not a product or a company. It is a protocol. Anyone can implement it. Anyone can build on it. It is free forever.

---

## What Problem Led to BXP?

Air pollution kills approximately 7 million people per year. The sensors to measure it exist and are getting cheaper every year. The barrier is not hardware — it is data fragmentation.

Today:
- Every sensor manufacturer uses a different data format
- Government monitoring agencies use different schemas than researchers
- Consumer applications can't use data from government networks
- A reading from Accra can't be compared to a reading from Delhi without custom conversion code

The result: enormous quantities of air quality data exist, but they cannot be used together. This wastes the potential of every sensor deployed, and prevents the kind of cross-border, multi-source analysis needed to understand and respond to air pollution at scale.

---

## Why Does Interoperability Matter?

Interoperability is the technical word for "can these systems talk to each other?" Right now, most air quality systems cannot.

This has real consequences:
- A hospital receiving a patient with respiratory symptoms cannot pull their recent exposure history from nearby sensors
- A researcher studying pollution in West Africa cannot combine government monitoring data with citizen sensor networks in a single analysis
- An application developer cannot build a tool that works globally — they must write a custom integration for every data source

BXP addresses this by defining a single data format that any source can write and any application can read. Once a sensor or data feed supports BXP, it instantly works with every BXP-compatible application — without any further negotiation.

---

## What Did the Creator Actually Build?

The following components have been built and are present in this repository:

### 1. BXP v2.0 Protocol Specification (`SPEC.md`)
A 1,300-line formal technical specification defining the complete BXP protocol: the data format, agent schema (31 atmospheric agents), five-stage data pipeline, REST API (20+ endpoints), privacy framework, health risk index, and governance model.

### 2. BXP Reference Server (`reference-server/`)
A working Python server that implements the BXP REST API. Accepts readings from any source, stores them in a SQLite database, computes health risk scores, enforces privacy controls, and serves a live dashboard showing a world map of readings and time-series charts.

The server also implements: device registration and authentication, community reports, cryptographic deletion, rate limiting, Prometheus metrics, and an embeddable widget.

### 3. Python SDK (`sdk/python/bxp_sdk.py`)
A complete developer library that makes it trivial to write `.bxp.json` files, calculate health risk scores, validate data against the BXP specification, and communicate with any BXP server — with both synchronous and asynchronous clients, and an offline queue for IoT sensors.

### 4. TypeScript SDK (`sdk/typescript/bxp-sdk.ts`)
A TypeScript implementation of the BXP SDK for web and Node.js developers.

### 5. CLI Tool (`cli/bxp_cli.py`)
A command-line tool supporting: generate, read, validate, submit, batch-submit, export (CSV/GeoJSON), HRI calculation, HTML map generation, and configuration management.

### 6. Sample Dataset (`datasets/sample_readings.bxp.json`)
Ten validated readings from major cities across six continents (Accra, Lagos, Delhi, Beijing, London, São Paulo, New York, Nairobi, Jakarta, Cairo), demonstrating BXP as a genuinely global data format.

### 7. Supporting Infrastructure
MQTT bridge for IoT sensor integration, Docker deployment configuration, Postman API collection, GitHub Actions CI, and complete protocol documentation.

---

## How Does BXP Work?

Every air quality measurement in BXP follows five stages:

| Stage | What Happens |
|-------|-------------|
| **LOCATE** | The measurement is given a geographic context — a geohash encoding the location to the nearest ~4.9 km cell |
| **DETECT** | The data source is classified by capability tier: phone sensor (Tier 1), consumer sensor (Tier 2), or reference instrument (Tier 3) |
| **INTERPRET** | Automated quality control checks the data for range violations, spikes, and inconsistencies; a quality flag is assigned |
| **PROTECT** | A composite health risk score (BXP_HRI) is calculated from all available agents, incorporating exposure duration and population vulnerability |
| **REPORT** | The reading is stored and made available through the standard REST API |

The BXP_HRI score translates raw measurements into a single number: 0 (clean) to 100 (hazardous emergency). It incorporates all measured agents simultaneously, weighted by their contribution to the global disease burden — something single-pollutant indices like AQI cannot do.

---

## What Evidence Exists?

| Evidence | Location |
|----------|----------|
| Protocol specification (1,300 lines) | `SPEC.md` |
| Reference server implementation | `reference-server/` |
| Python SDK (895 lines) | `sdk/python/bxp_sdk.py` |
| TypeScript SDK | `sdk/typescript/bxp-sdk.ts` |
| CLI tool (740+ lines) | `cli/bxp_cli.py` |
| Sample dataset (10 global cities) | `datasets/sample_readings.bxp.json` |
| MQTT bridge | `integrations/mqtt_bridge.py` |
| Docker deployment | `Dockerfile`, `docker-compose.yml` |
| API documentation | `docs/api_documentation.md` |
| Developer guide | `docs/developer_guide.md` |
| Changelog (v1.0 → v2.1) | `CHANGELOG.md` |
| Zenodo DOI (specification) | https://doi.org/10.5281/zenodo.18906812 |
| Zenodo DOI (implementation) | https://doi.org/10.5281/zenodo.18907003 |
| GitHub repository | https://github.com/bxpprotocol/bxp-spec |

---

## What Remains to Be Solved?

BXP is honest about what it has not yet achieved:

1. **Binary format** — The specification for a compact binary `.bxp` file is complete, but the software implementation of the encoder/decoder has not been written yet
2. **Federated network** — The design for how BXP nodes discover each other and share data is specified, but the peer-to-peer synchronisation code has not been implemented
3. **Embedded SDKs** — Arduino and ESP32 SDKs for hardware sensors are planned but not built
4. **External adoption** — No third-party has independently implemented BXP yet; the reference implementation is the only working implementation
5. **Clinical validation** — The BXP_HRI index has not been reviewed by epidemiologists or validated against health outcome data
6. **Formal governance** — The proposed BXP Foundation governance body does not yet exist

These are the natural limitations of independent research conducted by one person. The specification and reference implementation are the foundation. Broader adoption and external validation are the next step.

---

*Copyright 2026 Elvarin — Apache 2.0. The air is public. The data should be too.*
