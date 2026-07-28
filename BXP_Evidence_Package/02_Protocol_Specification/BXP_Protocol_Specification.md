# Breathe Exposure Protocol (BXP) Specification
## Version 2.0 — Formal Technical Reference

> **Status:** Active  
> **Author:** Elvarin  
> **Version:** 2.0  
> **Date:** March 2026  
> **License:** Apache 2.0  
> **DOI:** https://doi.org/10.5281/zenodo.18906812

---

## Abstract

BXP (Breathe Exposure Protocol) is an open, universal file system specification and data standard for the capture, storage, transmission, and interpretation of atmospheric exposure data. It defines the structural foundation upon which air quality applications, environmental monitoring systems, research databases, health platforms, and community reporting tools can interoperate using a single, standardised, open data layer.

BXP is a pure software protocol standard. Like HTTP, PDF, and MP3 — it requires no proprietary hardware, no centralised infrastructure, and no licensing fees. It runs on any device, any platform, any geography, at any scale.

---

## Implementation Status Legend

Throughout this document, components are labelled as follows:

| Label | Meaning |
|-------|---------|
| **[IMPLEMENTED]** | Fully working code exists in this repository |
| **[SPECIFIED]** | Fully defined in the specification; software implementation pending |
| **[PROPOSED]** | Design is outlined; detailed specification pending |
| **[FUTURE]** | Planned for a future version |

---

## Table of Contents

1. Terminology
2. Design Philosophy
3. File System Architecture
4. The .bxp File Format
5. Agent Schema
6. Protocol Stages
7. REST API Specification
8. Security & Privacy Framework
9. Community Reporting Layer
10. BXP Health Risk Index (BXP_HRI)
11. Governance & Versioning
12. Compatibility Matrix
13. Appendix A — Complete Agent Reference
14. Appendix B — Geohash Reference
15. Appendix C — Error Codes
16. Appendix D — Glossary

---

## 1. Terminology

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in RFC 2119.

| Term | Definition |
|------|------------|
| BXP Volume | A complete BXP file system instance on any storage substrate |
| Agent | Any atmospheric substance or biological entity tracked by BXP |
| Reading | A single point-in-time measurement record |
| Aggregate | A computed summary of multiple readings over time or space |
| Geohash | A compact geographic coordinate encoding system |
| BXP_HRI | BXP Health Risk Index — composite health risk score (0–100) |
| Container | A portable, self-verifying file bundling one or more readings |
| Device Token | Authentication credential issued to a data source |
| Quality Flag | A metadata tag describing data reliability |

---

## 2. Design Philosophy

BXP is built on six non-negotiable principles:

### 2.1 Universality **[IMPLEMENTED in reference server and SDK]**
BXP MUST work for any data source, any platform, any geography, and any scale.

### 2.2 Interoperability **[IMPLEMENTED — JSON format; SPECIFIED — binary format]**
Any BXP-compliant system MUST be able to read any BXP-compliant file regardless of origin.

### 2.3 Openness **[IMPLEMENTED]**
The standard is fully open. Apache 2.0 licensed. No fees, no closed sections, no gatekeepers. Forever.

### 2.4 Accessibility **[PARTIALLY IMPLEMENTED — Python, TypeScript; FUTURE — MicroPython, Arduino]**
BXP MUST be implementable on low-resource devices including basic smartphones and embedded systems.

### 2.5 Privacy-First **[IMPLEMENTED in reference server v2.1]**
Individual exposure records are private by default. Cryptographic controls operate at the file level.

### 2.6 Extensibility **[IMPLEMENTED via versioned namespaces]**
The standard MUST grow without breaking existing implementations. Backward compatibility is maintained across all MINOR versions.

---

## 3. File System Architecture **[SPECIFIED — logical structure defined; PROPOSED — physical implementation]**

A BXP volume is a logical file system structure. It can be implemented on any physical storage.

### 3.1 Root Structure

```
BXP:/
├── /meta/        — Volume identity, schema version, Merkle checksums
├── /locations/   — Geohash-based geographic hierarchy
├── /agents/      — Canonical pollutant definitions
├── /exposures/   — Device, personal, and aggregate exposure records
├── /devices/     — Device registry with calibration traceability
├── /alerts/      — Alert event system
├── /community/   — Community observation reports
├── /research/    — Research-grade dataset storage
└── /system/      — Audit logs, schema version control
```

*Note: The volume file system architecture is defined in the specification. The reference implementation uses a SQLite database rather than a physical BXP volume structure. The volume structure is the target for v3.0 or a dedicated storage implementation.*

---

## 4. The .bxp File Format

### 4.1 Overview **[JSON: IMPLEMENTED; Binary: SPECIFIED]**

Two representations exist, semantically identical and losslessly convertible:

- **Binary `.bxp`** — compact format with 32-byte header, designed for constrained devices
- **JSON `.bxp.json`** — human-readable format, designed for APIs and developer use

### 4.2 Binary Header (32 bytes) **[SPECIFIED]**

| Offset | Length | Field | Description |
|--------|--------|-------|-------------|
| 0x00 | 4 bytes | Magic Number | `0x42585000` ("BXP\0") |
| 0x04 | 2 bytes | Major Version | Schema major version (uint16 big-endian) |
| 0x06 | 2 bytes | Minor Version | Schema minor version (uint16 big-endian) |
| 0x08 | 1 byte | File Type | 0x01=reading, 0x02=aggregate, 0x03=agent, 0x04=device |
| 0x09 | 1 byte | Flags | bit0=compressed, bit1=encrypted, bit2=signed, bit3=draft |
| 0x0A | 2 bytes | Reserved | Must be 0x0000 in v2.0 |
| 0x0C | 8 bytes | Timestamp | Unix epoch microseconds (int64 big-endian) |
| 0x14 | 4 bytes | Payload Length | Payload size in bytes (uint32 big-endian) |
| 0x18 | 4 bytes | Header Checksum | CRC32 of bytes 0x00–0x17 |
| 0x1C | 4 bytes | Payload Checksum | CRC32 of entire payload |

### 4.3 Reading Record Schema (JSON) **[IMPLEMENTED]**

```json
{
  "bxpVersion": "2.0",
  "fileType": "reading",
  "deviceUuid": "550e8400-e29b-41d4-a716-446655440000",
  "geohash": "s1v0g",
  "latitude": 5.5571,
  "longitude": -0.1969,
  "timestampUs": 1710000000000000,
  "durationS": 60,
  "indoorOutdoor": "outdoor",
  "agents": [
    {
      "agentId": "PM2_5",
      "value": 47.3,
      "unit": "ug/m3",
      "uncertainty": 3.1,
      "method": "optical",
      "belowLod": false
    }
  ],
  "context": {
    "temperatureC": 28.4,
    "humidityPct": 72.1,
    "pressureHpa": 1012.3
  },
  "quality": {
    "flag": "UNVALIDATED",
    "confidence": 0.9,
    "qcMethod": "bxp-sdk-auto",
    "notes": null
  },
  "payloadHash": "sha256:..."
}
```

### 4.4 Required Fields for a Valid Reading **[IMPLEMENTED — validated in SDK and server]**

| Field | Requirement | Notes |
|-------|------------|-------|
| `bxpVersion` | REQUIRED | Must be "2.0" |
| `deviceUuid` | REQUIRED | UUID v4 |
| `geohash` | REQUIRED | Minimum precision 5 |
| `timestampUs` | REQUIRED | Unix epoch microseconds, UTC |
| `agents` | REQUIRED | At least one entry with `agentId` and `value` |
| `quality.flag` | REQUIRED | One of: VALIDATED, UNVALIDATED, SUSPECT, INVALID |

### 4.5 Quality Flags **[IMPLEMENTED]**

| Flag | Description |
|------|-------------|
| VALIDATED | Passed all automated QC checks |
| UNVALIDATED | Raw data, no QC applied |
| SUSPECT | Failed one or more QC checks |
| INVALID | Known bad data — do not use |

### 4.6 Verification Process **[IMPLEMENTED in SDK and server]**

1. Canonically serialize payload using sorted JSON keys, compact separators
2. Compute SHA-256 hash of the UTF-8 encoded serialization
3. Prefix with `"sha256:"` and store as `payloadHash`
4. On verification: recompute and compare against stored hash
5. If Ed25519 signature present: verify against device public key

---

## 5. Agent Schema **[IMPLEMENTED — schema defined; thresholds implemented in SDK and server]**

### 5.1 Particulate Matter

| Agent ID | Name | Unit | WHO Annual | WHO 24h |
|----------|------|------|-----------|---------|
| PM1 | Particulate Matter <1μm | μg/m³ | — | — |
| PM2_5 | Fine Particulate Matter <2.5μm | μg/m³ | 5 | 15 |
| PM10 | Coarse Particulate Matter <10μm | μg/m³ | 15 | 45 |
| BC | Black Carbon | μg/m³ | — | — |

### 5.2 Gaseous Pollutants

| Agent ID | Name | Unit | WHO Limit |
|----------|------|------|-----------|
| CO | Carbon Monoxide | ppm | 4 mg/m³ (24h) |
| CO2 | Carbon Dioxide | ppm | 1000 (indoor guideline) |
| NO2 | Nitrogen Dioxide | ppb | 10 μg/m³ annual |
| SO2 | Sulphur Dioxide | ppb | 40 μg/m³ (24h) |
| O3 | Ground-level Ozone | ppb | 100 μg/m³ (8h) |
| H2S | Hydrogen Sulphide | ppb | 7 ppb |
| NH3 | Ammonia | ppm | 25 ppm |

### 5.3 Volatile Organic Compounds

| Agent ID | Compound | Unit | Threshold | Classification |
|----------|----------|------|-----------|----------------|
| TVOC | Total VOC | ppb | 500 | Aggregate |
| BENZ | Benzene | ppb | 1 | Group 1 Carcinogen (IARC) |
| FORM | Formaldehyde | ppb | 8 | Group 1 Carcinogen (IARC) |
| TOLU | Toluene | ppm | 50 | Neurotoxin |

### 5.4 Biological, Heavy Metal, and Environmental Agents

*See Appendix A for the complete 31-agent reference.*

### 5.5 BXP_HRI (Derived Index) **[IMPLEMENTED]**

A composite 0–100 health risk score. See Section 10 for full specification.

---

## 6. Protocol Stages **[IMPLEMENTED — Stages 1–4 implemented in reference server]**

### Stage 1 — LOCATE
Every BXP record MUST be geographically contextualised. Minimum geohash precision: 5.

### Stage 2 — DETECT
BXP accepts three tiers of data sources: Tier 1 (phone, manual), Tier 2 (consumer sensors, satellite), Tier 3 (reference instruments).

### Stage 3 — INTERPRET
Automated QC rules: range validation, spike detection, flatline detection, humidity correction (Barkjohn correction for PM2.5 at RH >75%), cross-sensor consistency.

### Stage 4 — PROTECT
Six-level risk framework using BXP_HRI. See Section 10.

### Stage 5 — REPORT **[IMPLEMENTED in reference server v2.1]**
Community report schema combining sensor readings with human observations.

---

## 7. REST API Specification **[IMPLEMENTED — reference server v2.1]**

### 7.1 Base URL

```
https://[host]/bxp/v2/
```

### 7.2 Implemented Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Interactive dashboard |
| GET | `/bxp/v2/health` | Node health and status |
| GET | `/bxp/v2/city/{city}` | Live city data via AQICN |
| GET | `/bxp/v2/readings` | List readings (with filters) |
| POST | `/bxp/v2/readings` | Submit readings (returns 201) |
| GET | `/bxp/v2/readings/{id}` | Get reading by ID |
| DELETE | `/bxp/v2/readings/{id}` | Delete with cryptographic proof |
| GET | `/bxp/v2/readings/{id}/verify` | Integrity check |
| GET | `/bxp/v2/locations/{geohash}/latest` | Latest reading for location |
| GET | `/bxp/v2/locations/{geohash}/history` | Historical readings |
| GET | `/bxp/v2/locations/{geohash}/aggregate` | k≥5 anonymised aggregate |
| POST | `/bxp/v2/devices/register` | Register device |
| GET | `/bxp/v2/devices/{uuid}` | Get device metadata |
| POST | `/bxp/v2/community/reports` | Submit community report |
| GET | `/bxp/v2/community/reports` | Get community reports |
| GET | `/bxp/v2/search` | Search by city or coordinates |
| GET | `/bxp/v2/nodes` | Federated node registry |
| GET | `/metrics` | Prometheus format metrics |
| GET | `/bxp/v2/widget/{city}` | Embeddable iframe widget |

### 7.3 Standard Response Envelope

```json
{
  "status": "ok",
  "bxpVersion": "2.0",
  "data": {},
  "errors": []
}
```

### 7.4 Authentication

Bearer token authentication. Three token classes: Device Token (per-UUID, permanent), User Token (personal records, 30-day), API Key (administrative). Anonymous submissions are accepted but marked.

### 7.5 Rate Limiting **[IMPLEMENTED]**

- Submissions: 30 per minute per IP
- City lookups: 60 per minute per IP
- Device registrations: 5 per minute per IP

---

## 8. Security & Privacy Framework **[IMPLEMENTED in reference server v2.1]**

### 8.1 Privacy Rules (Non-Negotiable)

- Personal exposure records are **private by default**
- Person identifiers are NEVER stored in plain form — only SHA-256 hashes
- Location precision for personal records defaults to Geohash 5
- Community aggregates are k-anonymised before publication (minimum k=5)
- Users can permanently delete all personal records via single API call
- Deletion is cryptographically verifiable and irreversible (deletion proof returned)

### 8.2 Encryption Standards **[SPECIFIED — design defined; not all implemented in reference server]**

| Data Type | Encryption | Status |
|-----------|------------|--------|
| Personal records at rest | AES-256-GCM | Specified |
| Data in transit | TLS 1.3 | Specified (deployment-dependent) |
| Device signatures | Ed25519 | Specified |
| Volume integrity | SHA-256 Merkle tree | Specified |
| Payload integrity | SHA-256 | **Implemented** |

### 8.3 Data Integrity Model **[IMPLEMENTED — Layer 2 record-level hashing]**

Layer 1 (file-level CRC32) requires binary format. Layer 2 (SHA-256 per record) is implemented. Layers 3–4 (volume Merkle tree, audit log) are specified for future implementation.

### 8.4 Compliance Framework **[DESIGNED — not formally audited]**

BXP is designed for compliance with GDPR, CCPA, POPIA, PDPA, and HIPAA through its privacy architecture. Formal compliance assessment has not been conducted.

---

## 9. Community Reporting Layer **[IMPLEMENTED in reference server v2.1]**

Community reports enable human observers to submit structured qualitative observations alongside optional sensor data. The report schema includes: location, timestamp, visual observations (smoke, haze, visibility), olfactory observations, symptom reports, 12 standardised event tags (open_burning, harmattan, wildfire, etc.), photo attachment metadata, and free-text description.

A five-stage automated QC pipeline processes community reports: geospatial clustering, cross-validation with sensor readings, outlier detection, reporter reliability scoring, and abuse detection.

---

## 10. BXP Health Risk Index (BXP_HRI) **[IMPLEMENTED]**

### 10.1 Agent Weights

| Agent | Weight | Basis |
|-------|--------|-------|
| PM2.5 | 0.35 | Highest global DALY burden (WHO 2021) |
| PM10 | 0.15 | Significant respiratory burden |
| NO2 | 0.15 | High urban prevalence |
| O3 | 0.12 | Respiratory effects, summer peaks |
| CO | 0.10 | Acute toxicity |
| SO2 | 0.05 | Industrial variation |
| TVOC | 0.04 | Indoor carcinogen concern |

### 10.2 Calculation

```
agent_risk(i)  = min(1.0, value(i) / WHO_threshold(i))
raw_HRI        = Σ (agent_risk(i) × weight(i))
BXP_HRI        = min(100, raw_HRI × 100 × duration_factor × vulnerability_factor)
```

Duration factors: 1h → 1.0, 8h → 1.2, 24h → 1.5  
Vulnerability factors: general → 1.0, sensitive → 1.3

### 10.3 Risk Levels

| Level | BXP_HRI | Color | General Population Guidance |
|-------|---------|-------|----------------------------|
| CLEAN | 0–20 | #00C851 | No restrictions |
| MODERATE | 21–40 | #FFBB33 | Sensitive groups: limit heavy exertion |
| ELEVATED | 41–60 | #FF8800 | Reduce outdoor exertion |
| HIGH | 61–75 | #CC0000 | N95 outdoors, close windows |
| VERY_HIGH | 76–90 | #9B0000 | Avoid outdoor activity |
| HAZARDOUS | 91–100 | #4A0000 | Health emergency |

---

## 11. Governance & Versioning

### 11.1 BXP Foundation **[PROPOSED — does not currently exist as a formal organisation]**

The specification proposes governance by an independent, non-profit open standards body — the BXP Foundation — modelled on established open standards bodies such as the IETF and W3C. This governance structure is an aspiration for the protocol's long-term management. It does not currently exist.

### 11.2 Versioning Policy **[IMPLEMENTED]**

BXP uses semantic versioning: MAJOR.MINOR.PATCH. MAJOR changes require 18 months advance notice. MINOR changes are backward compatible. All changes go through a public RFC process.

---

## 12. Compatibility Matrix

| Standard | BXP Compatibility | Status |
|----------|------------------|--------|
| US AQI | BXP_HRI maps to AQI_US derived field | Designed |
| WHO AQG 2021 | All thresholds aligned | Implemented |
| HL7 FHIR R4 | Exposure records map to FHIR Observation | Designed, not documented |
| OGC SensorThings | Compatible observation model | Designed |
| GDPR/CCPA | Privacy framework designed for compliance | Designed, not audited |

---

## Appendix A — Complete Agent Reference

| Agent ID | Full Name | Category | Unit | WHO Limit |
|----------|-----------|----------|------|-----------|
| PM1 | Particulate Matter <1μm | Particulates | μg/m³ | — |
| PM2_5 | Fine Particulate Matter | Particulates | μg/m³ | 5 annual |
| PM10 | Coarse Particulate Matter | Particulates | μg/m³ | 15 annual |
| BC | Black Carbon | Particulates | μg/m³ | — |
| CO | Carbon Monoxide | Gas | ppm | 4 mg/m³ 24h |
| CO2 | Carbon Dioxide | Gas | ppm | 1000 indoor |
| NO2 | Nitrogen Dioxide | Gas | ppb | 10 μg/m³ annual |
| NO | Nitric Oxide | Gas | ppb | — |
| SO2 | Sulphur Dioxide | Gas | ppb | 40 μg/m³ 24h |
| O3 | Ground-level Ozone | Gas | ppb | 100 μg/m³ 8h |
| H2S | Hydrogen Sulphide | Gas | ppb | 7 ppb |
| NH3 | Ammonia | Gas | ppm | 25 ppm |
| TVOC | Total VOC | VOC | ppb | 500 ppb |
| BENZ | Benzene | VOC | ppb | No safe level (IARC Group 1) |
| FORM | Formaldehyde | VOC | ppb | 8 ppb |
| TOLU | Toluene | VOC | ppm | 50 ppm |
| XYLE | Xylene | VOC | ppm | 100 ppm |
| NAPH | Naphthalene | VOC | ppb | 9.4 ppb |
| MOLD_S | Mold Spores | Biological | spores/m³ | 500 indoor |
| POLL_G | Grass Pollen | Biological | grains/m³ | 50 moderate |
| POLL_T | Tree Pollen | Biological | grains/m³ | 100 high |
| BACT_T | Total Bacteria | Biological | CFU/m³ | 500 indoor |
| DUST_M | Dust Mite Allergen | Biological | ng/m³ | 2 ng/m³ |
| PB | Lead | Heavy Metal | μg/m³ | 0.5 annual |
| HG | Mercury | Heavy Metal | μg/m³ | 1 annual |
| AS | Arsenic | Heavy Metal | ng/m³ | 6.6 annual |
| TEMP | Temperature | Environmental | °C | — |
| RH | Relative Humidity | Environmental | % | — |
| PRESS | Atmospheric Pressure | Environmental | hPa | — |
| UV | UV Index | Environmental | index | — |
| BXP_HRI | BXP Health Risk Index | Derived | 0–100 | — |

---

## Appendix B — Geohash Reference

| Precision | Cell Width | Cell Height | BXP Use |
|-----------|------------|-------------|---------|
| 5 chars | ~4.9 km | ~4.9 km | Minimum valid BXP reading |
| 6 chars | ~1.2 km | ~0.61 km | Neighbourhood level |
| 7 chars | ~153 m | ~153 m | Recommended for fixed sources |
| 8 chars | ~38 m | ~19 m | Street level |
| 9 chars | ~4.8 m | ~4.8 m | High-resolution personal sensors |

---

## Appendix C — Error Codes

| Code | HTTP | Meaning |
|------|------|---------|
| BXP_4001 | 400 | Geohash precision below minimum (5) |
| BXP_4002 | 400 | Missing required field |
| BXP_4003 | 400 | Invalid agent ID |
| BXP_4004 | 400 | Unit not recognised for agent |
| BXP_4005 | 400 | Timestamp outside acceptable range |
| BXP_4006 | 400 | Payload hash mismatch |
| BXP_4010 | 401 | Missing or invalid authentication token |
| BXP_4290 | 429 | Rate limit exceeded |
| BXP_5000 | 500 | Internal server error |
| BXP_5030 | 503 | BXP volume temporarily unavailable |

---

## Appendix D — Glossary

| Term | Definition |
|------|------------|
| Agent | Any atmospheric substance or biological entity BXP can track |
| BXP Volume | A complete BXP file system instance on any storage substrate |
| Container | A portable self-verifying file bundling one or more readings |
| Geohash | A compact geographic coordinate encoding for spatial indexing |
| BXP_HRI | BXP Health Risk Index — composite health risk score 0–100 |
| Reading | A single point-in-time measurement record |
| Quality Flag | Metadata tag: VALIDATED / UNVALIDATED / SUSPECT / INVALID |
| k-anonymisation | No aggregate published with fewer than k sources |
| Tier 1/2/3 | Source capability tiers: Tier 1 phone/manual → Tier 3 reference instrument |
| DALY | Disability-Adjusted Life Year — WHO measure of disease burden |

---

## Origin & Authorship

BXP was conceived and first implemented by Elvarin on February 15, 2026. This document is the official BXP v2.0 Technical Specification.

---

## References

World Health Organization. (2021). *WHO Global Air Quality Guidelines.* Geneva: WHO.  
Simcoe, T. (2012). Standard setting committees. *American Economic Review, 102*(1), 305–336.

*Copyright 2026 Elvarin — Apache 2.0 License*  
*The air is public. The data should be too.*
