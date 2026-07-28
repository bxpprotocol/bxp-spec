# BXP Evidence Portfolio
## A Structured Overview for External Reviewers

**Project:** Breathe Exposure Protocol (BXP)  
**Creator:** Elvarin  
**Category:** Independent research in open data standards for public health  
**Repository:** https://github.com/bxpprotocol/bxp-spec  
**Specification DOI:** https://doi.org/10.5281/zenodo.18906812  
**Implementation DOI:** https://doi.org/10.5281/zenodo.18907003

---

## Project Overview

BXP (Breathe Exposure Protocol) is an independently developed open data standard for atmospheric exposure information — a universal file format and REST API specification that allows any air quality measurement, from any source, anywhere in the world, to be represented, stored, and exchanged in a consistent, machine-readable format.

The project emerged from an investigation into why air quality data — despite the proliferation of affordable sensors — remains fragmented, incompatible, and therefore underused. BXP proposes and partially demonstrates that this fragmentation can be eliminated through an open protocol standard: a common language for breath exposure data that no company owns and anyone can implement.

---

## Original Problem

Air pollution kills approximately 7 million people per year (WHO, 2021). The sensors to measure it exist and are affordable. The barrier is not hardware — it is data fragmentation. Every sensor manufacturer, monitoring agency, and research network uses incompatible data formats. A sensor in Accra cannot feed a dashboard in Nairobi. A citizen reading in Delhi cannot contribute to a government pollution map. The data exists, but it cannot be used together.

---

## Original Insight

The insight that led to BXP was recognising this as an interoperability problem rather than a measurement problem. The solution was not to build a better sensor or a better application — it was to define a common data language, in the same way that HTTP solved the web's interoperability problem and MP3 solved audio fragmentation.

---

## What I Personally Did

Everything in this repository was independently created by Elvarin. This includes:

- Identifying and documenting the air quality data interoperability problem
- Designing the protocol architecture and data model from first principles
- Writing the formal BXP v2.0 specification (1,300 lines)
- Building the reference server in Python (FastAPI, 1,877 lines)
- Building the Python SDK (895 lines)
- Building the TypeScript SDK
- Building the CLI tool (740+ lines)
- Writing the API documentation, developer guide, and architecture documentation
- Publishing the specification and implementation to Zenodo with permanent DOIs
- Conducting the systematic 50-item gap analysis between v1.0 and v2.0
- Creating the sample dataset representing 10 global cities

---

## Research Conducted

- Investigation of existing air quality data standards and their limitations (US AQI, European CAQI, OpenAQ, OGC SensorThings, HL7 FHIR)
- Study of WHO Air Quality Guidelines 2021 for threshold values
- Study of DALY (Disability-Adjusted Life Year) burden data for HRI weighting
- Analysis of interoperability approaches in other domains (HTTP, PDF, MP3, DICOM)
- Investigation of privacy frameworks for personal health data (GDPR, CCPA, POPIA)
- Study of cryptographic techniques for data integrity (SHA-256, Ed25519)

---

## Technical Work

| Component | Technology | Lines | Status |
|-----------|------------|-------|--------|
| Protocol specification | Markdown | ~1,300 | Complete |
| Reference server | Python/FastAPI/SQLite | ~1,877 | Complete |
| Python SDK | Python | ~895 | Complete |
| TypeScript SDK | TypeScript | ~400 | Complete |
| CLI tool | Python | ~740+ | Complete |
| MQTT bridge | Python | ~200+ | Complete |
| Docker deployment | Docker | — | Complete |
| Sample dataset | JSON | 250 lines | Complete |
| API documentation | Markdown | ~200 | Complete |
| Developer guide | Markdown | ~200 | Complete |

---

## Protocol Development

The protocol design work included:

- Defining a canonical agent schema for 31 atmospheric substances across 7 categories
- Designing the BXP_HRI composite health risk index with WHO-derived weights
- Specifying a binary file format with 32-byte fixed header (magic number, version, flags, checksums)
- Designing a five-stage data pipeline (LOCATE → DETECT → INTERPRET → PROTECT → REPORT)
- Specifying 20+ REST API endpoints with full request/response schemas
- Designing a privacy framework with geohash floors, k-anonymisation, and cryptographic deletion
- Specifying a community reporting layer with 12 standardised event tags
- Designing a governance model with RFC process and versioning policy

---

## Prototype / Implementation

The reference server is a functional prototype that:
- Accepts readings from any source via HTTP
- Validates data against the BXP specification
- Computes BXP_HRI health risk scores
- Stores readings in SQLite with SHA-256 payload hashes
- Enforces privacy controls (geohash floor, k≥5 anonymity, cryptographic deletion)
- Serves an interactive web dashboard with a world map and time-series charts
- Can be started with four Python packages and a single command

---

## Documentation

Seven documentation artefacts were created:
1. `SPEC.md` — formal protocol specification
2. `docs/api_documentation.md` — API reference
3. `docs/developer_guide.md` — developer quick-start
4. `docs/protocol_overview.md` — protocol overview
5. `CHANGELOG.md` — development history
6. `CONTRIBUTING.md` — contribution guide
7. This evidence package (9 documents)

---

## Evidence of Iteration

The development history demonstrates clear iteration:

- **v1.0 (February 15, 2026):** First prototype — portable containers with SHA-256 verification, offline-first design
- **Gap analysis:** 50-item systematic audit identifying missing protocol components
- **v2.0 (March 2026):** Complete specification — full agent schema, REST API, privacy framework, HRI with modifiers, governance model
- **Reference server v2.1:** All critical gaps from the audit addressed — persistence, auth, privacy, rate limiting, dashboard, community reports, etc.
- **SDK and CLI expansion:** Async client, offline queue, TypeScript SDK, batch operations added

This is documented in `CHANGELOG.md` and the development notes.

---

## Current Status

BXP v2.0 is a complete open protocol specification with a working reference implementation, Python SDK, TypeScript SDK, CLI tool, and ecosystem tooling. It has been published to Zenodo with permanent DOIs. The GitHub repository is public.

**Honest assessment of maturity:** BXP is a research prototype and protocol proposal. The binary file format is specified but not yet implemented in software. The federated network is designed but not yet built. No third-party has independently implemented the protocol. These are the natural limitations of independent research conducted by one person.

---

## Future Direction

- Binary format implementation
- Federated node synchronisation
- Arduino/ESP32 SDKs for hardware sensors
- BXP-STREAM real-time data extension
- External review of BXP_HRI by atmospheric scientists/epidemiologists
- Engagement with sensor manufacturers or monitoring organisations

---

## Evidence Table

| Evidence Item | What It Demonstrates | Location |
|--------------|---------------------|----------|
| `SPEC.md` (1,300 lines) | Protocol design and systems thinking | GitHub root |
| Reference server (`reference-server/`) | Technical implementation ability | GitHub |
| Python SDK (`sdk/python/bxp_sdk.py`) | Software development | GitHub |
| TypeScript SDK | Cross-platform development | `sdk/typescript/` |
| CLI tool (`cli/bxp_cli.py`) | Tooling and developer experience design | GitHub |
| `CHANGELOG.md` | Iterative development and improvement | GitHub root |
| Sample dataset (10 cities) | Global scope of the protocol | `datasets/` |
| Development gap analysis (50 items) | Systematic thinking and self-critique | `attached_assets/` |
| MQTT bridge | IoT integration thinking | `integrations/` |
| Docker deployment | Production-ready thinking | Root |
| Zenodo DOI (spec) | Independent publication | doi.org/10.5281/zenodo.18906812 |
| Zenodo DOI (implementation) | Independent publication | doi.org/10.5281/zenodo.18907003 |
| GitHub repository | Public, reproducible, open-source | github.com/bxpprotocol/bxp-spec |
| This evidence package | Communication and research documentation | `BXP_Evidence_Package/` |

---

*Copyright 2026 Elvarin — Apache 2.0. The air is public. The data should be too.*
