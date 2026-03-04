 BXP Technical Specification v2.0

> **Breathe Exposure Protocol — Complete Technical Reference**
> Status: Active | Version: 2.0 | License: Apache 2.0

---

## Table of Contents

1. [Abstract](#1-abstract)
2. [Terminology](#2-terminology)
3. [Design Philosophy](#3-design-philosophy)
4. [File System Architecture](#4-file-system-architecture)
5. [The .bxp File Format](#5-the-bxp-file-format)
6. [Agent Schema](#6-agent-schema)
7. [Protocol Stages](#7-protocol-stages)
8. [REST API Specification](#8-rest-api-specification)
9. [Security & Privacy Framework](#9-security--privacy-framework)
10. [Community Reporting Layer](#10-community-reporting-layer)
11. [Implementation Guide](#11-implementation-guide)
12. [Governance & Versioning](#12-governance--versioning)
13. [BXP Health Risk Index](#13-bxp-health-risk-index)
14. [Compatibility Matrix](#14-compatibility-matrix)
15. [Appendix A — Agent Reference](#appendix-a--complete-agent-reference)
16. [Appendix B — Geohash Reference](#appendix-b--geohash-reference)
17. [Appendix C — Error Codes](#appendix-c--error-codes)
18. [Appendix D — Glossary](#appendix-d--glossary)

---

## 1. Abstract

BXP (Breathe Exposure Protocol) is an open, universal file system
specification and data standard for the capture, storage, transmission,
and interpretation of atmospheric exposure data.

It defines the structural foundation upon which air quality applications,
governmental monitoring systems, research databases, health platforms,
and community reporting tools can interoperate — using a single,
standardized, open data layer.

BXP is a pure software protocol standard. Like HTTP, PDF, MP3, and SSL —
it requires no proprietary hardware, no centralized infrastructure, and
no licensing fees. It runs on any device, any platform, any geography,
at any scale.

**BXP is to breath exposure data what HTTP is to the web.**

### 1.1 The Problem

Air pollution causes 7 million premature deaths annually — more than
HIV, malaria, and tuberculosis combined (WHO, 2024). The tools to
measure, track, and respond to air pollution exist. The problem is
the data infrastructure does not.

Four critical failures define the current ecosystem:

| Failure | Description |
|---------|-------------|
| Fragmentation | Every device, app, and agency uses incompatible formats |
| Proprietary lock-in | Closed ecosystems with expensive licensing |
| Geographic inequality | Monitoring concentrated in wealthy nations |
| No universal standard | No open protocol exists for air exposure data |

A sensor in Accra cannot speak to a hospital in Nairobi.
A citizen reading in Delhi cannot contribute to a government map.
A researcher in London cannot access ground-truth data from Lagos.

BXP eliminates this fragmentation permanently.

### 1.2 Scope

BXP v2.0 covers all outdoor and indoor atmospheric exposure data
including particulate matter, gaseous pollutants, volatile organic
compounds, biological agents, heavy metal particulates, and
environmental variables. Extension into waterborne and soil
contamination is planned for v3.0.

---

## 2. Terminology

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT",
"SHOULD", "SHOULD NOT", "RECOMMENDED", "MAY", and "OPTIONAL" in this
document are to be interpreted as described in RFC 2119.

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

## 3. Design Philosophy

BXP is built on six non-negotiable principles:

### 3.1 Universality
BXP MUST work for any data source, any platform, any geography,
and any scale — from a single phone to a planetary monitoring network.

### 3.2 Interoperability
Any BXP-compliant system MUST be able to read any BXP-compliant file
regardless of origin, device, or platform.

### 3.3 Openness
The standard is fully open. No licensing fees. No closed sections.
No gatekeepers. MIT and Apache 2.0 licensed. Forever free.

### 3.4 Accessibility
BXP MUST be implementable on low-resource devices including basic
smartphones, embedded systems, and offline environments.

### 3.5 Privacy-First
Individual exposure records are private by default. Cryptographic
controls operate at the file level. No surveillance assumptions
are permitted.

### 3.6 Extensibility
The standard MUST grow without breaking existing implementations.
All extensions use versioned namespaces. Backward compatibility
is maintained across all MINOR versions.

---

## 4. File System Architecture

A BXP volume is a logical file system structure. It can be implemented
on any physical storage: local disk, cloud object store (S3, GCS),
distributed ledger, peer-to-peer network, or embedded flash memory.
The logical structure remains identical regardless of substrate.

### 4.1 Root Structure

```
BXP:/
├── /meta/
├── /locations/
├── /agents/
├── /exposures/
├── /devices/
├── /alerts/
├── /community/
├── /research/
└── /system/
```

### 4.2 /meta — Volume Metadata

```
/meta/
├── volume.bxp         — volume identity, version, owner, created
├── schema.bxp         — schema version in use
├── index.bxp          — master index of all records
├── checksums.bxp      — Merkle tree integrity hashes
└── extensions/        — custom extension definitions
```

Every BXP volume MUST contain a valid `/meta/volume.bxp` file.

### 4.3 /locations — Geographic Hierarchy

```
/locations/
└── [continent]/
    └── [country-iso]/
        └── [region]/
            └── [geohash-5]/          (~4.9km × 4.9km cell)
                └── [geohash-7]/      (~153m × 153m cell)
                    ├── current.bxp
                    ├── history/
                    │   └── YYYY/
                    │       └── MM/
                    │           └── DD.bxp
                    ├── events/
                    └── profile.bxp
```

### 4.4 /agents — Pollutant Definitions

```
/agents/
├── particulates/
│   ├── PM1.agent.bxp
│   ├── PM2_5.agent.bxp
│   └── PM10.agent.bxp
├── gases/
│   ├── CO.agent.bxp
│   ├── CO2.agent.bxp
│   ├── NO2.agent.bxp
│   ├── SO2.agent.bxp
│   ├── O3.agent.bxp
│   ├── H2S.agent.bxp
│   └── NH3.agent.bxp
├── vocs/
│   ├── TVOC.agent.bxp
│   ├── benzene.agent.bxp
│   ├── formaldehyde.agent.bxp
│   └── toluene.agent.bxp
├── biological/
│   ├── mold.agent.bxp
│   ├── pollen.agent.bxp
│   ├── bacteria.agent.bxp
│   └── virus.agent.bxp
├── heavy_metals/
│   ├── lead.agent.bxp
│   ├── mercury.agent.bxp
│   └── arsenic.agent.bxp
└── environmental/
    ├── temperature.agent.bxp
    ├── humidity.agent.bxp
    ├── pressure.agent.bxp
    └── uv_index.agent.bxp
```

### 4.5 /exposures — Exposure Records

```
/exposures/
├── devices/
│   └── [device-uuid]/
│       ├── raw/               — immutable raw readings
│       └── processed/         — calibrated, validated readings
├── persons/                   — encrypted by default
│   └── [sha256-of-person-id]/
│       ├── timeline.bxp
│       ├── risk_profile.bxp
│       └── health_events/
└── aggregates/
    ├── hourly/
    ├── daily/
    ├── monthly/
    └── annual/
```

### 4.6 /devices — Device Registry

```
/devices/
└── [device-uuid]/
    ├── identity.bxp
    ├── calibration/
    │   └── YYYY-MM-DD.cal.bxp
    ├── location_history/
    └── health/
```

### 4.7 /community — Community Reports

```
/community/
├── reports/
│   └── [geohash-7]/
│       └── YYYY-MM-DD/
│           └── [report-uuid].bxp
└── events/
    └── [event-uuid]/
        ├── metadata.bxp
        └── attachments/
```

---

## 5. The .bxp File Format

### 5.1 Overview

The `.bxp` file format is BXP's native data format — a structured,
versioned, optionally compressed and encrypted container. Two
representations exist:

- **Binary `.bxp`** — compact, efficient, designed for devices
- **JSON `.bxp.json`** — human-readable, designed for APIs

Both are semantically identical. Any BXP implementation MUST support
both and MUST be capable of lossless conversion between them.

### 5.2 Binary Header (32 bytes)

| Offset | Length | Field | Description |
|--------|--------|-------|-------------|
| 0x00 | 4 bytes | Magic Number | `0x42585000` ("BXP\0") |
| 0x04 | 2 bytes | Major Version | Schema major version (uint16 big-endian) |
| 0x06 | 2 bytes | Minor Version | Schema minor version (uint16 big-endian) |
| 0x08 | 1 byte | File Type | 0x01=reading, 0x02=aggregate, 0x03=agent, 0x04=device, 0x05=alert, 0x06=meta |
| 0x09 | 1 byte | Flags | bit0=compressed, bit1=encrypted, bit2=signed, bit3=draft |
| 0x0A | 2 bytes | Reserved | Must be 0x0000 in v2.0 |
| 0x0C | 8 bytes | Timestamp | Unix epoch microseconds (int64 big-endian) |
| 0x14 | 4 bytes | Payload Length | Payload size in bytes (uint32 big-endian) |
| 0x18 | 4 bytes | Header Checksum | CRC32 of bytes 0x00–0x17 |
| 0x1C | 4 bytes | Payload Checksum | CRC32 of entire payload |

### 5.3 Reading Record Schema

```json
{
  "bxpVersion": "2.0",
  "fileType": "reading",
  "deviceUuid": "550e8400-e29b-41d4-a716-446655440000",
  "geohash": "s1v0g",
  "latitude": 5.5571,
  "longitude": -0.1969,
  "altitudeM": 61.0,
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
    },
    {
      "agentId": "CO",
      "value": 1.2,
      "unit": "ppm",
      "uncertainty": 0.1,
      "method": "electrochemical",
      "belowLod": false
    }
  ],
  "context": {
    "temperatureC": 28.4,
    "humidityPct": 72.1,
    "pressureHpa": 1012.3,
    "windSpeedMs": 2.1,
    "windDirDeg": 220
  },
  "quality": {
    "flag": "VALIDATED",
    "confidence": 0.94,
    "qcMethod": "automated-v2",
    "notes": ""
  },
  "signature": ""
}
```

### 5.4 Container Schema

A BXP Container is a portable, self-verifying file bundling one
or more readings. Derived from BXP v1.0 container specification.

```json
{
  "containerSchema": "bxp.container.v2",
  "payload": {
    "protocol": "Breathe Exposure Protocol",
    "version": "2.0",
    "owner": "user",
    "generatedAt": "2026-03-04T08:00:00Z",
    "readings": []
  },
  "payloadHash": "sha256:...",
  "signature": "ed25519:...",
  "verification": {
    "method": "sha256+ed25519",
    "status": "Verified"
  }
}
```

### 5.5 Verification Process

Verification MUST follow this exact process:

1. Canonically serialize payload using sorted JSON keys
2. Compute SHA-256 hash of the UTF-8 encoded serialization
3. Compare computed hash to `payloadHash`
4. If hashes match: `verification.status = "Verified"`
5. If hashes do not match: `verification.status = "Tampered"`
6. If Ed25519 signature present: verify against device public key

### 5.6 Quality Flags

| Flag | Code | Description |
|------|------|-------------|
| VALIDATED | 0 | Passed all automated QC checks |
| UNVALIDATED | 1 | Raw data, no QC applied |
| SUSPECT | 2 | Failed one or more QC checks |
| INVALID | 3 | Known bad data — do not use |

---

## 6. Agent Schema

### 6.1 Particulate Matter

| Agent ID | Name | Unit | WHO Annual | WHO 24h | Health Impact |
|----------|------|------|-----------|---------|---------------|
| PM1 | Particulate Matter <1μm | μg/m³ | — | — | Deep lung penetration, bloodstream entry |
| PM2_5 | Fine Particulate Matter <2.5μm | μg/m³ | 5 | 15 | Cardiovascular disease, lung cancer, stroke |
| PM10 | Coarse Particulate Matter <10μm | μg/m³ | 15 | 45 | Respiratory inflammation, asthma |
| BC | Black Carbon | μg/m³ | — | — | Climate forcing; linked to PM2.5 effects |

### 6.2 Gaseous Pollutants

| Agent ID | Name | Unit | WHO Limit | Primary Sources |
|----------|------|------|-----------|-----------------|
| CO | Carbon Monoxide | ppm | 4 mg/m³ (24h) | Combustion, generators, cooking fires |
| CO2 | Carbon Dioxide | ppm | 1000 (indoor) | Respiration, combustion |
| NO2 | Nitrogen Dioxide | ppb | 10 μg/m³ annual | Vehicle exhaust, power plants |
| SO2 | Sulphur Dioxide | ppb | 40 μg/m³ (24h) | Coal burning, industrial |
| O3 | Ground-level Ozone | ppb | 100 μg/m³ (8h) | Photochemical reaction |
| H2S | Hydrogen Sulphide | ppb | 7 ppb | Sewage, industrial waste |
| NH3 | Ammonia | ppm | 25 ppm | Agriculture, waste decomposition |

### 6.3 Volatile Organic Compounds

| Agent ID | Compound | Unit | Threshold | Classification |
|----------|----------|------|-----------|----------------|
| TVOC | Total VOC | ppb | >500 ppb | Aggregate |
| BENZ | Benzene | ppb | >1 ppb | Group 1 Carcinogen (IARC) |
| FORM | Formaldehyde | ppb | >8 ppb | Group 1 Carcinogen (IARC) |
| TOLU | Toluene | ppm | >50 ppm | Neurotoxin |
| XYLE | Xylene | ppm | >100 ppm | Neurotoxin |
| NAPH | Naphthalene | ppb | >9.4 ppb | Possible carcinogen |

### 6.4 Biological Agents

| Agent ID | Agent | Unit | Guideline |
|----------|-------|------|-----------|
| MOLD_S | Mold Spores | spores/m³ | >500 indoor concern |
| POLL_G | Grass Pollen | grains/m³ | >50 moderate season |
| POLL_T | Tree Pollen | grains/m³ | >100 high season |
| BACT_T | Total Bacteria | CFU/m³ | >500 indoor guideline |
| DUST_M | Dust Mite Allergen | ng/m³ | >2 ng/m³ |

### 6.5 Heavy Metals

| Agent ID | Element | Unit | WHO Guideline |
|----------|---------|------|---------------|
| PB | Lead | μg/m³ | 0.5 μg/m³ annual |
| HG | Mercury | μg/m³ | 1 μg/m³ (1-year) |
| AS | Arsenic | ng/m³ | 6.6 ng/m³ annual |

### 6.6 Environmental Variables

| Agent ID | Variable | Unit |
|----------|----------|------|
| TEMP | Temperature | °C |
| RH | Relative Humidity | % |
| PRESS | Atmospheric Pressure | hPa |
| UV | UV Index | index (0–11+) |

### 6.7 Derived Indices

| Index ID | Name | Basis | Scale |
|----------|------|-------|-------|
| AQI_US | US Air Quality Index | PM2.5, PM10, CO, NO2, SO2, O3 | 0–500 |
| AQI_EU | European AQI | PM2.5, PM10, NO2, SO2, O3 | 1–5 bands |
| BXP_HRI | BXP Health Risk Index | All available agents, weighted | 0–100 |

---

## 7. Protocol Stages

### Stage 1 — LOCATE

Every BXP record MUST be geographically contextualized.

**Location Requirements:**

| Requirement | Rule |
|-------------|------|
| Minimum precision | Geohash precision 5 (~4.9km cell) |
| Recommended precision | Geohash precision 7 (~153m cell) |
| High precision | Geohash precision 9 (~4.8m cell) |
| Coordinates | WGS84 decimal degrees where available |
| Indoor flag | MUST be set for all records |
| Altitude | SHOULD be included where elevation affects readings |

**Location Acquisition Methods:**

| Method | Code | Accuracy |
|--------|------|----------|
| GPS/GNSS | GPS | 3–10m |
| Network/Cell | NET | 50–500m |
| Manual entry | MAN | Variable |
| IP geolocation | IPG | City-level (flagged LOW_PRECISION) |

### Stage 2 — DETECT

BXP accepts data from any source. No proprietary hardware required.

**Data Source Tiers:**

| Tier | Sources | Quality Flag |
|------|---------|-------------|
| Tier 1 | Phone-native sensors, manual observation, existing apps | UNVALIDATED |
| Tier 2 | Consumer sensors, government open data feeds, satellites | UNVALIDATED → VALIDATED |
| Tier 3 | Reference instruments, certified monitoring stations | VALIDATED |

All tiers produce valid BXP data. Quality flags reflect reliability.
A network of 10,000 Tier 1 sources provides more spatial coverage
than 10 Tier 3 sources, even accounting for individual error.

**Required Fields for a Valid Reading:**

- `deviceUuid` — REQUIRED
- `geohash` — minimum precision 5 — REQUIRED
- `timestampUs` — Unix epoch microseconds UTC — REQUIRED
- At least one `agents` entry with `value`, `unit`, `agentId` — REQUIRED
- `quality.flag` — must be explicitly set — REQUIRED

### Stage 3 — INTERPRET

**Automated QC Rules (PM2.5 example):**

| Check | Rule | Result |
|-------|------|--------|
| Range | 0 ≤ PM2.5 ≤ 1000 μg/m³ | Outside range → INVALID |
| Spike | Change >200 μg/m³ in <60s | → SUSPECT |
| Flatline | Identical value >30 min | → SUSPECT |
| Humidity | RH >75% | Apply Barkjohn correction |
| Cross-sensor | >300% difference from nearby source | → SUSPECT |

**Unit Normalization:**
All readings MUST be converted to BXP canonical units:
- Particulates: μg/m³ at standard conditions (25°C, 1 atm)
- Gases: ppb at standard conditions
- Temperature corrections MUST be applied before storage

### Stage 4 — PROTECT

**BXP Risk Level Framework:**

| Level | BXP_HRI | AQI Equiv | Color | General Population | Sensitive Groups |
|-------|---------|-----------|-------|-------------------|-----------------|
| CLEAN | 0–20 | 0–50 | Green | No restrictions | No restrictions |
| MODERATE | 21–40 | 51–100 | Yellow | Acceptable for most | Limit heavy exertion |
| ELEVATED | 41–60 | 101–150 | Orange | Reduce heavy outdoor exertion | Avoid outdoor exertion |
| HIGH | 61–75 | 151–200 | Red | N95 outdoors. Close windows. | Avoid outdoors. Air purifier. |
| VERY HIGH | 76–90 | 201–300 | Purple | Avoid outdoors. N95 mandatory. | Stay indoors. Seek medical help if symptomatic. |
| HAZARDOUS | 91–100 | 301–500 | Maroon | Emergency. Stay indoors. | Evacuate to cleaner air if possible. |

### Stage 5 — REPORT

Community reports differ from device readings in that they include
qualitative human observations alongside quantitative data.

**Report Components:**
- Sensor readings (optional but recommended)
- Visual observations: smoke color, haze band, visibility
- Olfactory observations: odor type and intensity
- Symptom reports: correlated with location and time
- Event tags: `open_burning`, `traffic_jam`, `industrial_accident`
- Photo attachments with GPS EXIF metadata

---

## 8. REST API Specification

### 8.1 Base URL

```
https://[host]/bxp/v2/
```

### 8.2 Endpoints

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| GET | `/locations/{geohash}/current` | Current readings for location | No |
| GET | `/locations/{geohash}/history` | Historical readings | No |
| GET | `/locations/{geohash}/agents/{agentId}` | Specific agent at location | No |
| POST | `/readings` | Submit one or more readings | Device Token |
| GET | `/readings/{readingId}` | Get reading by ID | No |
| GET | `/agents` | List all supported agents | No |
| GET | `/agents/{agentId}` | Full agent specification | No |
| POST | `/devices/register` | Register a new device or source | API Key |
| GET | `/devices/{uuid}` | Get device metadata | Device Token |
| POST | `/devices/{uuid}/calibration` | Submit calibration record | Device Token |
| GET | `/alerts` | Active alerts for a location | No |
| POST | `/community/reports` | Submit community report | User Token |
| GET | `/search` | Search by bounding box, time, agent | No |
| GET | `/stats/{geohash}` | Statistical summary for location | No |
| DELETE | `/persons/{hash}` | Permanently delete personal records | User Token |

### 8.3 Query Parameters

Standard parameters supported across all GET /locations endpoints:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `start` | ISO 8601 datetime | 24h ago | Start of query window |
| `end` | ISO 8601 datetime | now | End of query window |
| `agents` | comma-separated string | all | Agent IDs to include |
| `quality` | enum | UNVALIDATED | Minimum quality flag |
| `limit` | integer | 100 | Max records returned (max 10,000) |
| `offset` | integer | 0 | Pagination offset |
| `format` | enum | json | Response format: json, bxp, csv |
| `resolution` | integer 5–9 | source | Geohash precision for aggregation |

### 8.4 Standard Response Envelope

Every API response MUST follow this structure:

```json
{
  "status": "ok",
  "bxpVersion": "2.0",
  "requestId": "req_a1b2c3d4",
  "timestamp": "2026-03-04T08:00:00Z",
  "data": {},
  "meta": {
    "totalCount": 1842,
    "returnedCount": 100,
    "offset": 0,
    "queryDurationMs": 34
  },
  "errors": []
}
```

### 8.5 Error Response Format

```json
{
  "status": "error",
  "bxpVersion": "2.0",
  "requestId": "req_a1b2c3d4",
  "timestamp": "2026-03-04T08:00:00Z",
  "data": null,
  "errors": [
    {
      "code": "BXP_4001",
      "message": "Geohash precision below minimum required (5)",
      "field": "geohash"
    }
  ]
}
```

### 8.6 Authentication

Three token classes are recognized by BXP:

| Token Type | Scope | Lifespan | How to Obtain |
|------------|-------|----------|---------------|
| Device Token | Write readings for one UUID | Permanent until revoked | Issued at device registration |
| User Token | Personal records, community reports | 30 days, refreshable | OAuth 2.0 flow |
| API Key | Administrative operations | Permanent until revoked | Issued to volume administrators |

All tokens MUST be passed in the `Authorization` header:

```
Authorization: Bearer [token]
```

### 8.7 Rate Limits

| Token Type | Read Limit | Write Limit |
|------------|------------|-------------|
| No auth (public) | 1,000 req/hour | — |
| Device Token | 10,000 req/hour | 1,000 readings/minute |
| User Token | 5,000 req/hour | 100 reports/hour |
| API Key | Unlimited | Unlimited |

Responses include rate limit headers:

```
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 847
X-RateLimit-Reset: 1710003600
```

---

## 9. Security & Privacy Framework

### 9.1 Privacy Architecture

BXP treats individual exposure data as sensitive personal health
information. The following rules are NON-NEGOTIABLE in any
BXP-compliant implementation:

- Personal exposure records are **private by default**
- Person identifiers are NEVER stored in plain form
- Only SHA-256 hashes of user-controlled identifiers are stored
- Location precision for personal records defaults to Geohash 5
- Community aggregates are k-anonymized before publication (minimum k=5)
- Users can permanently delete all personal records via single API call
- Deletion is cryptographically verifiable and irreversible

### 9.2 Encryption Standards

| Data Type | Encryption | Key Derivation |
|-----------|------------|----------------|
| Personal records at rest | AES-256-GCM | PBKDF2 from user credentials |
| Data in transit | TLS 1.3 minimum | — |
| Device readings (optional signing) | Ed25519 | Device key pair at registration |
| Volume integrity | SHA-256 Merkle tree | — |

BXP servers MUST NOT accept connections below TLS 1.2.
TLS 1.3 is REQUIRED for all personal data endpoints.

### 9.3 Data Integrity Model

BXP uses a four-layer integrity model:

**Layer 1 — File Level**
Every .bxp file includes CRC32 checksums of both header
and payload. Corruption is detectable on any read.

**Layer 2 — Record Level**
Optional Ed25519 cryptographic signature per reading,
verifiable against the device's registered public key.
Signed readings cannot be forged or altered without detection.

**Layer 3 — Volume Level**
`/meta/checksums.bxp` maintains a Merkle tree of all file
checksums. Enables efficient tamper detection across an
entire volume without reading every file.

**Layer 4 — Audit Log**
All write operations are logged in `/system/audit.log`
with timestamp, source UUID, operation type, and record hash.
Audit logs are append-only and cryptographically chained.

### 9.4 Regulatory Compliance

BXP is designed for compliance with:

| Regulation | Region | Key BXP Feature |
|------------|--------|-----------------|
| GDPR | European Union | Right to erasure, data portability, purpose limitation |
| CCPA | California, USA | Right to access, right to delete, opt-out of sale |
| POPIA | South Africa | Data minimization, lawful processing |
| PDPA | Multiple Asian nations | Consent-based collection, breach notification |
| HIPAA | USA (health data) | Encryption at rest and in transit, audit logs |

---

## 10. Community Reporting Layer

### 10.1 Overview

Community reports combine human observation with structured data.
They recognize that a person who can see smoke, smell chemicals,
or feel eye irritation is a valid sensor — and that their
observations, aggregated across thousands of people, produce
intelligence that no hardware network can replicate.

### 10.2 Community Report Schema

```json
{
  "reportType": "community",
  "reporterHash": "sha256:a3f9...",
  "geohash": "s1v0g",
  "latitude": 5.5571,
  "longitude": -0.1969,
  "timestampUs": 1710000000000000,
  "observations": {
    "visibleSmoke": true,
    "smokeColor": "black",
    "hazeBand": true,
    "visibilityKm": 2.1,
    "odorPresent": true,
    "odorType": "burning_rubber",
    "odorIntensity": 3
  },
  "symptoms": {
    "eyeIrritation": true,
    "coughing": true,
    "headache": false,
    "breathingDifficulty": false,
    "skinIrritation": false
  },
  "eventTags": [
    "open_burning",
    "traffic_congestion"
  ],
  "sensorReadings": [],
  "photoAttachments": [
    {
      "hash": "sha256:b7c2...",
      "mimeType": "image/jpeg",
      "sizeBytes": 204800,
      "gpsLat": 5.5571,
      "gpsLon": -0.1969
    }
  ],
  "freeText": "Large fire visible at industrial site 200m north-west",
  "confidence": 0.8,
  "bxpVersion": "2.0"
}
```

### 10.3 Valid Event Tags

| Tag | Description |
|-----|-------------|
| `open_burning` | Open waste or biomass burning |
| `traffic_congestion` | Heavy stationary traffic |
| `industrial_accident` | Industrial facility incident |
| `dust_storm` | Windblown dust event |
| `harmattan` | Harmattan dust season (West Africa) |
| `wildfire` | Wildfire smoke |
| `construction` | Active construction site |
| `generator_exhaust` | Generator operation nearby |
| `cooking_smoke` | Charcoal or biomass cooking |
| `chemical_spill` | Chemical release event |
| `sewage` | Sewage exposure event |
| `pesticide_spray` | Agricultural or urban spraying |

### 10.4 Community QC Pipeline

Community reports pass through five automated quality checks:

**Check 1 — Geospatial Clustering**
Reports within 500m and 30 minutes of each other are clustered.
Clustered events receive confidence boosts proportional to
the number of independent reporters.

**Check 2 — Cross-Validation**
Reports overlapping in space-time with sensor readings are
cross-validated. Consistency increases confidence of both
the report and the sensor reading.

**Check 3 — Outlier Detection**
Reports inconsistent with surrounding data are flagged SUSPECT
and queued for manual review before inclusion in aggregates.

**Check 4 — Reporter Reliability Scoring**
Over time, reporters whose observations consistently align with
verified data receive higher base confidence weights.
New reporters start at confidence 0.5. Maximum is 1.0.

**Check 5 — Abuse Detection**
Automated detection of repeated identical submissions,
geographically impossible submissions, timestamp manipulation,
and bot-pattern behavior. Flagged accounts are suspended
pending review.

---

## 11. Implementation Guide

### 11.1 Implementing a BXP Data Source

Any application, device, or system that produces BXP-formatted
data is a BXP data source. No hardware is required.

**Minimum Viable Implementation — 6 Steps:**

**Step 1 — Generate UUID**
Generate a UUID v4 for your source. This UUID is permanent.

```python
import uuid
device_uuid = str(uuid.uuid4())
# Example: "550e8400-e29b-41d4-a716-446655440000"
```

**Step 2 — Register with a BXP Volume**

```python
import requests

registration = {
    "deviceUuid": device_uuid,
    "sourceType": "phone_app",
    "capabilities": ["PM2_5", "TEMP", "RH"],
    "accuracyClass": "tier1",
    "bxpVersion": "2.0"
}

response = requests.post(
    "https://[bxp-server]/bxp/v2/devices/register",
    json=registration,
    headers={"Authorization": "Bearer [api-key]"}
)

device_token = response.json()["data"]["deviceToken"]
```

**Step 3 — Build a Reading Record**

```python
from datetime import datetime, timezone
import time

reading = {
    "bxpVersion": "2.0",
    "fileType": "reading",
    "deviceUuid": device_uuid,
    "geohash": "s1v0g",
    "latitude": 5.5571,
    "longitude": -0.1969,
    "timestampUs": int(time.time() * 1_000_000),
    "durationS": 60,
    "indoorOutdoor": "outdoor",
    "agents": [
        {
            "agentId": "PM2_5",
            "value": 47.3,
            "unit": "ug/m3",
            "uncertainty": 3.1,
            "method": "optical",
            "belowLod": False
        }
    ],
    "context": {
        "temperatureC": 28.4,
        "humidityPct": 72.1,
        "pressureHpa": 1012.3
    },
    "quality": {
        "flag": "UNVALIDATED",
        "confidence": 0.7
    }
}
```

**Step 4 — Compute and Attach Hash**

```python
import json
import hashlib

payload_str = json.dumps(reading, sort_keys=True)
payload_hash = hashlib.sha256(
    payload_str.encode("utf-8")
).hexdigest()

container = {
    "containerSchema": "bxp.container.v2",
    "payload": reading,
    "payloadHash": f"sha256:{payload_hash}",
    "verification": {
        "method": "sha256",
        "status": "Unverified"
    }
}
```

**Step 5 — Submit**

```python
response = requests.post(
    "https://[bxp-server]/bxp/v2/readings",
    json=container,
    headers={"Authorization": f"Bearer {device_token}"}
)
```

**Step 6 — Handle Offline / Buffer Locally**

```python
import json
import os
from pathlib import Path

BUFFER_PATH = Path("bxp_buffer/")
BUFFER_PATH.mkdir(exist_ok=True)

def submit_with_fallback(container, token):
    try:
        response = requests.post(
            "https://[bxp-server]/bxp/v2/readings",
            json=container,
            headers={"Authorization": f"Bearer {token}"},
            timeout=10
        )
        response.raise_for_status()
        return True
    except Exception:
        # Buffer locally — file named by timestamp
        ts = container["payload"]["timestampUs"]
        buffer_file = BUFFER_PATH / f"{ts}.bxp.json"
        with open(buffer_file, "w") as f:
            json.dump(container, f)
        return False
```

### 11.2 Implementing a BXP Application

Any application reading or displaying BXP data MUST:

- Display quality flags clearly — never present SUSPECT or
  INVALID data as reliable without explicit labeling
- Use BXP canonical units with clear unit labels on all displays
- Implement the BXP risk level framework (Section 7, Stage 4)
- Use the correct BXP_HRI color scheme for risk visualization
- Never cache personal exposure data beyond the immediate session
- Respect user deletion requests immediately and completely

### 11.3 Reference Implementations

| Implementation | Language | Repository |
|----------------|----------|------------|
| bxp-server | Python 3.11+ | github.com/bxpprotocol/bxp-server |
| bxp-server-node | Node.js 20+ | github.com/bxpprotocol/bxp-server-node |
| bxp-sdk-python | Python 3.11+ | github.com/bxpprotocol/bxp-sdk-python |
| bxp-sdk-js | JavaScript/TypeScript | github.com/bxpprotocol/bxp-sdk-js |
| bxp-sdk-arduino | C/C++ Arduino | github.com/bxpprotocol/bxp-sdk-arduino |
| bxp-sdk-esp32 | C/C++ ESP-IDF | github.com/bxpprotocol/bxp-sdk-esp32 |
| bxp-mobile | React Native | github.com/bxpprotocol/bxp-mobile |

---

## 12. Governance & Versioning

### 12.1 The BXP Foundation

BXP is governed by the BXP Foundation — an independent,
non-profit open standards body. Its mandate is to maintain,
evolve, and promote the BXP specification in the public
interest with no commercial bias and no single controlling entity.

**Structure:**

| Body | Role |
|------|------|
| Technical Steering Committee | 7 elected members. Responsible for all specification changes and version releases |
| Working Groups | Domain-specific: hardware, software, privacy, health, community |
| Advisory Board | WHO, national environmental agencies, manufacturers, academic institutions, civil society |
| Open Community | Any individual or organization may participate and propose changes |

### 12.2 Versioning Policy

BXP uses semantic versioning — MAJOR.MINOR.PATCH:

| Change Type | Version Impact | Compatibility |
|-------------|---------------|---------------|
| Bug fixes, clarifications | PATCH | Full backward and forward compatibility |
| New optional fields | MINOR | Backward compatible. Existing implementations do not break. |
| Breaking changes | MAJOR | 18 months advance notice required. Dual-version support during transition. |

### 12.3 RFC Process

All specification changes follow the BXP RFC process:

1. Any person submits RFC proposal via GitHub
2. Relevant Working Group reviews over 30-day public comment period
3. Technical Steering Committee votes: accept, reject, or return for revision
4. Accepted RFCs incorporated into next appropriate version release

---

## 13. BXP Health Risk Index

### 13.1 Overview

BXP_HRI is BXP's native composite health risk score on a 0–100
scale. Unlike single-pollutant indices such as AQI, BXP_HRI
incorporates all available agents with WHO-derived weighting,
exposure duration, and population vulnerability modifiers.

### 13.2 Agent Weights

| Agent | Weight | Basis |
|-------|--------|-------|
| PM2.5 | 0.35 | Highest global DALY burden (WHO 2021) |
| PM10 | 0.15 | Significant respiratory burden |
| NO2 | 0.15 | High urban prevalence, lung inflammation |
| O3 | 0.12 | Strong respiratory effects, summer peaks |
| CO | 0.10 | Acute toxicity, high developing-world burden |
| SO2 | 0.05 | Regional industrial variation |
| TVOC | 0.04 | Indoor carcinogen concern |
| Biological | 0.04 | Contextual, high in humid environments |

### 13.3 Calculation Formula

**Step 1 — Normalize each agent to 0–1 risk scale:**

```
agent_risk(i) = min(1.0, value(i) / WHO_threshold(i))
```

**Step 2 — Compute weighted sum:**

```
raw_HRI = Σ ( agent_risk(i) × weight(i) )
```

**Step 3 — Apply duration and vulnerability modifiers:**

```
BXP_HRI = min(100, raw_HRI × 100 × duration_factor
                              × vulnerability_factor)
```

**Duration factors:**

| Averaging Period | Factor |
|-----------------|--------|
| 1-hour average | 1.0 |
| 8-hour average | 1.2 |
| 24-hour average | 1.5 |

**Vulnerability factors:**

| Population | Factor |
|------------|--------|
| General population | 1.0 |
| Sensitive groups (children, elderly, respiratory conditions) | 1.3 |

### 13.4 Python Reference Implementation

```python
WHO_THRESHOLDS = {
    "PM2_5": 15.0,
    "PM10": 45.0,
    "NO2": 25.0,
    "O3": 100.0,
    "CO": 4.0,
    "SO2": 40.0,
    "TVOC": 500.0,
}

WEIGHTS = {
    "PM2_5": 0.35,
    "PM10": 0.15,
    "NO2": 0.15,
    "O3": 0.12,
    "CO": 0.10,
    "SO2": 0.05,
    "TVOC": 0.04,
}

DURATION_FACTORS = {
    "1h": 1.0,
    "8h": 1.2,
    "24h": 1.5,
}

VULNERABILITY_FACTORS = {
    "general": 1.0,
    "sensitive": 1.3,
}

def calculate_bxp_hri(agents, duration="1h", population="general"):
    raw_hri = 0.0
    for agent_id, value in agents.items():
        if agent_id in WHO_THRESHOLDS and agent_id in WEIGHTS:
            risk = min(1.0, value / WHO_THRESHOLDS[agent_id])
            raw_hri += risk * WEIGHTS[agent_id]
    duration_factor = DURATION_FACTORS.get(duration, 1.0)
    vulnerability_factor = VULNERABILITY_FACTORS.get(population, 1.0)
    bxp_hri = min(100.0, raw_hri * 100 * duration_factor
                                       * vulnerability_factor)
    return round(bxp_hri, 2)


# Example usage
agents = {
    "PM2_5": 47.3,
    "NO2": 38.0,
    "CO": 1.2,
}

hri = calculate_bxp_hri(agents, duration="1h", population="general")
print(f"BXP_HRI: {hri}")
# Output: BXP_HRI: 34.21  →  MODERATE
```

---

## 14. Compatibility Matrix

| Standard | Organization | BXP Compatibility |
|----------|-------------|-------------------|
| AQI | US EPA | BXP_HRI maps directly. AQI_US is a supported derived field. |
| WHO Air Quality Guidelines 2021 | World Health Organization | All BXP thresholds align with WHO 2021 guidelines. |
| HL7 FHIR R4 | HL7 International | BXP exposure records map to FHIR Observation resources. |
| OGC SensorThings API | Open Geospatial Consortium | BXP implements a compatible observation model. |
| OpenAQ | OpenAQ | BXP can ingest and re-export OpenAQ data in standard format. |
| IEC 62484 | International Electrotechnical Commission | BXP binary format compatible with IEC sensor data standard. |
| Schema.org | W3C Community Group | BXP JSON uses Schema.org vocabulary where applicable. |
| GDPR | European Union | Privacy framework designed for full compliance. |

---

## Appendix A — Complete Agent Reference

| Agent ID | Full Name | Category | Unit | WHO Limit |
|----------|-----------|----------|------|-----------|
| PM1 | Particulate Matter <1μm | Particulates | μg/m³ | — |
| PM2_5 | Particulate Matter <2.5μm | Particulates | μg/m³ | 5 annual |
| PM10 | Particulate Matter <10μm | Particulates | μg/m³ | 15 annual |
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
| BENZ | Benzene | VOC | ppb | No safe level |
| FORM | Formaldehyde | VOC | ppb | 8 ppb |
| TOLU | Toluene | VOC | ppm | 50 ppm |
| XYLE | Xylene | VOC | ppm | 100 ppm |
| NAPH | Naphthalene | VOC | ppb | 9.4 ppb |
| MOLD_S | Mold Spores | Biological | spores/m³ | 500 indoor |
| POLL_G | Grass Pollen | Biological | grains/m³ | 50 moderate |
| POLL_T | Tree Pollen | Biological | grains/m³ | 100 high |
| BACT_T | Total Airborne Bacteria | Biological | CFU/m³ | 500 indoor |
| DUST_M | Dust Mite Allergen | Biological | ng/m³ | 2 ng/m³ |
| PB | Lead | Heavy Metal | μg/m³ | 0.5 annual |
| HG | Mercury | Heavy Metal | μg/m³ | 1 annual |
| AS | Arsenic | Heavy Metal | ng/m³ | 6.6 annual |
| TEMP | Temperature | Environmental | °C | — |
| RH | Relative Humidity | Environmental | % | — |
| PRESS | Atmospheric Pressure | Environmental | hPa | — |
| UV | UV Index | Environmental | index | — |
| AQI_US | US Air Quality Index | Derived | 0–500 | — |
| BXP_HRI | BXP Health Risk Index | Derived | 0–100 | — |

---

## Appendix B — Geohash Reference

| Precision | Characters | Cell Width | Cell Height | BXP Use |
|-----------|------------|------------|-------------|---------|
| 1 | 1 | ~5,000 km | ~5,000 km | Continental aggregates only |
| 2 | 2 | ~1,250 km | ~625 km | Country aggregates |
| 3 | 3 | ~156 km | ~156 km | Regional aggregates |
| 4 | 4 | ~39 km | ~20 km | City aggregates |
| 5 | 5 | ~4.9 km | ~4.9 km | Minimum valid BXP reading |
| 6 | 6 | ~1.2 km | ~0.61 km | Neighborhood level |
| 7 | 7 | ~153 m | ~153 m | Recommended for fixed sources |
| 8 | 8 | ~38 m | ~19 m | Street level |
| 9 | 9 | ~4.8 m | ~4.8 m | BXP-HIGHRES personal sensors |

---

## Appendix C — Error Codes

| Code | HTTP Status | Meaning |
|------|-------------|---------|
| BXP_4001 | 400 | Geohash precision below minimum (5) |
| BXP_4002 | 400 | Missing required field |
| BXP_4003 | 400 | Invalid agent ID |
| BXP_4004 | 400 | Unit not recognized for agent |
| BXP_4005 | 400 | Timestamp outside acceptable range |
| BXP_4006 | 400 | Payload hash mismatch — container tampered |
| BXP_4007 | 400 | Schema version not supported |
| BXP_4010 | 401 | Missing or invalid authentication token |
| BXP_4011 | 401 | Device token revoked |
| BXP_4030 | 403 | Insufficient permissions for operation |
| BXP_4040 | 404 | Reading or resource not found |
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
| Geohash | A compact geographic coordinate encoding used for spatial indexing |
| BXP_HRI | BXP Health Risk Index — composite health risk score 0–100 |
| Reading | A single point-in-time measurement record from one source |
| Aggregate | A computed summary of multiple readings over time or space |
| Device Token | Authentication credential for a data source writing to BXP |
| Community Report | A human-submitted observation record |
| Calibration Record | Links device readings to a reference standard at a point in time |
| Quality Flag | Metadata tag describing data reliability: VALIDATED through INVALID |
| k-anonymization | Privacy technique — no aggregate published with fewer than k sources |
| Tier 1/2/3 | BXP source capability tiers — Tier 1 phone/manual, Tier 3 reference |
| DALY | Disability-Adjusted Life Year — WHO measure of disease burden |
| Geohash-7 | ~153m × 153m geographic cell — BXP recommended precision |
| Prior Art | Publicly documented evidence of an invention before any patent claim |

---

## Origin & Authorship

BXP was conceived and first implemented by Elvarin on
February 15, 2026. The original v1 specification established
the foundational concepts of user-owned data, offline-first
architecture, portable containers, and SHA-256 verification.

This document is the official BXP v2.0 Technical Specification
— a direct continuation of that original work.

---

*Copyright 2026 Elvarin — Licensed under Apache 2.0*
*The air is public. The data should be too.*
```

