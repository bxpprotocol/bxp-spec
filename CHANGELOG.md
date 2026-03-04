# BXP Changelog

All notable changes to the Breathe Exposure Protocol are documented
in this file. The format follows [Keep a Changelog](https://keepachangelog.com)
and this project adheres to [Semantic Versioning](https://semver.org).

---

## [2.0.0] — March 2026

### The Official Standard

This release represents the complete BXP specification — a full
architectural expansion of the original v1 concept into a
production-ready, globally deployable open standard.

### Added

**File System Architecture**
- Complete BXP:// volume structure with 9 top-level directories
- /meta — volume identity, schema versioning, Merkle tree checksums
- /locations — geohash-based geographic hierarchy (precision 5–9)
- /agents — canonical pollutant and biological agent definitions
- /exposures — device, personal, and aggregate exposure records
- /devices — device registry with calibration traceability
- /alerts — alert event system
- /community — community observation reports
- /research — research-grade dataset storage
- /system — audit logs, system files, schema version control

**File Format**
- Binary .bxp format with 32-byte fixed header
- Magic number 0x42585000 for universal file identification
- CRC32 integrity checksums at both header and payload level
- Optional compression flag (bit0) and encryption flag (bit1)
- Optional Ed25519 cryptographic signing flag (bit2)
- JSON .bxp.json representation — semantically identical to binary
- Lossless conversion between binary and JSON representations
- Container schema v2 — direct evolution of v1 container

**Agent Schema**
- 31 atmospheric agents fully specified across 7 categories
- Particulates: PM1, PM2.5, PM10, Black Carbon
- Gases: CO, CO2, NO2, NO, SO2, O3, H2S, NH3
- Volatile Organics: TVOC, Benzene, Formaldehyde, Toluene, Xylene, Naphthalene
- Biological: Mold Spores, Grass Pollen, Tree Pollen, Total Bacteria, Dust Mite Allergen
- Heavy Metals: Lead, Mercury, Arsenic
- Environmental: Temperature, Humidity, Pressure, UV Index
- Derived: AQI_US, BXP Health Risk Index (BXP_HRI)
- All thresholds aligned with WHO Air Quality Guidelines 2021

**Protocol Stages**
- Stage 1 LOCATE — geohash precision requirements and location acquisition methods
- Stage 2 DETECT — three-tier source classification system (Tier 1/2/3)
- Stage 3 INTERPRET — automated QC rules, unit normalization, humidity correction
- Stage 4 PROTECT — six-level risk framework (CLEAN through HAZARDOUS)
- Stage 5 REPORT — community observation schema with event tagging

**REST API**
- 15 endpoints fully specified
- Standard response envelope with requestId, meta, and errors
- Three authentication token classes: Device, User, API Key
- Rate limiting framework with standard response headers
- Complete error code system (BXP_4001 through BXP_5030)
- Support for json, bxp, and csv response formats
- Geohash resolution parameter for spatial aggregation

**Security & Privacy**
- AES-256-GCM encryption for personal records at rest
- TLS 1.3 mandatory for all data in transit
- Ed25519 cryptographic signatures for reading integrity
- SHA-256 Merkle tree for volume-level tamper detection
- Append-only cryptographically chained audit logs
- Person identifiers stored as SHA-256 hashes only — never plain
- k-anonymization for community aggregates (minimum k=5)
- Single-call permanent personal data deletion
- GDPR, CCPA, POPIA, PDPA, HIPAA compliance framework

**Community Reporting Layer**
- Full community report schema with qualitative observation fields
- 12 standardized event tags including harmattan and generator_exhaust
- Five-stage automated QC pipeline
- Reporter reliability scoring system (0.5 to 1.0)
- Geospatial clustering for correlated event detection
- Abuse and spam detection system

**BXP Health Risk Index**
- BXP_HRI composite score (0–100) across all available agents
- WHO-derived agent weighting (8 agents, weights sum to 1.0)
- Duration modifiers: 1h (1.0×), 8h (1.2×), 24h (1.5×)
- Vulnerability modifiers: general (1.0×), sensitive groups (1.3×)
- Full Python reference implementation included

**Governance**
- BXP Foundation structure defined
- Technical Steering Committee (7 elected members)
- Working Groups: hardware, software, privacy, health, community
- Advisory Board framework: WHO, agencies, manufacturers, academia
- Semantic versioning policy with 18-month MAJOR change notice
- Open RFC process for all specification changes

**Compatibility**
- US EPA AQI — BXP_HRI maps directly
- WHO Air Quality Guidelines 2021 — full alignment
- HL7 FHIR R4 — exposure records map to Observation resources
- OGC SensorThings API — compatible observation model
- OpenAQ — ingest and re-export in standard format
- IEC 62484 — binary format compatibility
- Schema.org / JSON-LD — vocabulary alignment

**Implementation**
- 6-step minimum viable implementation guide
- Python code examples for all core operations
- Offline buffering pattern for low-connectivity environments
- 7 reference implementation repositories defined

---

## [1.0.0] — February 15, 2026 — FROZEN

### The Origin

This is where BXP began. Conceived, designed, and implemented
by Elvarin on February 15, 2026. The v1 specification established
the foundational concepts that all future versions are built upon.

This version is permanently frozen. It is preserved as the
original public record of BXP's creation.

### Established in v1

**Core Concept**
- Breathe Exposure Protocol — the name, the vision, the purpose
- User-owned data by default — no implicit transmission permitted
- Offline-first architecture — no network required for operation
- Sensor-agnostic design — works with any data source
- Forward-extensible format — built to grow without breaking

**Exposure Event Schema (bxp.exposure_event.v1)**
- event_id — UUID per exposure event
- timestamp_utc — ISO 8601 UTC timestamp
- location — latitude and longitude
- exposure_vector — oxygen, nitrogen, pollution, pollen, acidity
- notes — optional human-readable context
- Partial records permitted — timestamp-only events are valid

**Container Schema (bxp.container.v1)**
- protocol — "Breathe Exposure Protocol"
- version — protocol version string
- owner — data ownership declaration (default: "user")
- generated_at — container creation timestamp
- events — array of Exposure Event v1 objects
- payload_hash — SHA-256 of canonical JSON payload
- signature — cryptographic signature of payload hash
- verification — method, status (Verified / Tampered / Unverified)

**Verification Protocol**
- Canonical serialization using sorted JSON keys
- SHA-256 hashing of UTF-8 encoded payload
- Self-signing permitted in v1
- Three verification states: Verified, Unverified, Tampered

**Guarantees**
- Data is user-owned by default
- No implicit data transmission permitted
- No surveillance assumptions
- Offline-first
- Forward-extensible without breaking v1

**Working Implementation**
- Python reference implementation included in v1
- UUID generation for event identity
- SHA-256 hashing and self-signing
- Container build and verify functions
- File export to .bxp.txt format
- Verified working on date of publication

---

## Upcoming

### [2.1.0] — Q2 2026 (Planned)
- Python SDK (bxp-sdk-python)
- JavaScript/TypeScript SDK (bxp-sdk-js)
- Arduino SDK (bxp-sdk-arduino)
- ESP32 SDK (bxp-sdk-esp32)
- React Native mobile reference app
- BXP-STREAM real-time data extension
- Enhanced community QC algorithms

### [3.0.0] — 2027 (Planned)
- Waterborne contamination extension
- Soil contamination extension
- IoT mesh networking protocol
- Satellite data integration layer
- AI-powered exposure forecasting
- BXP-HEALTH extension — HL7 FHIR full mapping
- BXP-HIGHRES extension — precision 9 personal sensors

---

*Copyright 2026 Elvarin — Apache 2.0 License*
*The air is public. The data should be too.*
```
