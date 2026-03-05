# BXP — Breathe Exposure Protocol

> The universal open standard for atmospheric exposure data.
> No hardware required. Runs on any device. Free forever.

**Author:** Elvarin
**First Published:** February 15, 2026
**Current Version:** 2.0 (Active Development)
**License:** Apache 2.0
**Status:** Open Standard — Accepting Contributors

---

## What is BXP?

BXP is a pure software protocol standard — like HTTP, PDF, or MP3.

It defines a universal file system architecture and data format for
the capture, storage, transmission, and interpretation of atmospheric
exposure data. No sensors required. No hardware required. No
centralized infrastructure required. Runs on any phone, any device,
any platform, anywhere in the world.

BXP unifies data from government monitoring stations, satellites,
existing sensor applications, and community reports into one open,
portable, verifiable standard format.

**BXP is to breath exposure data what HTTP is to the web.**

---

## The Problem

Air pollution kills 7 million people every year. That is more than
HIV, malaria, and tuberculosis combined.

The technology to measure, track, and respond to air pollution
exists. Sensors are cheap. Connectivity is near-universal. Data
processing capacity is abundant.

And yet the global response remains fragmented, uncoordinated,
and ineffective — not because the tools do not exist, but because
the data infrastructure does not.

Today's air quality ecosystem has four critical failures:

- **Fragmentation** — every device, app, and agency stores data
  in a different incompatible format
- **Proprietary lock-in** — major platforms maintain closed
  ecosystems with expensive licensing
- **Geographic inequality** — monitoring infrastructure concentrated
  in wealthy nations; the populations most affected have the least data
- **No universal standard** — unlike HTTP for web data or DICOM for
  medical imaging, no open standard exists for air exposure data

A sensor in Accra cannot speak to a hospital in Nairobi.
A citizen reading in Delhi cannot contribute to a government map.
A researcher in London cannot access ground-truth data from Lagos.

BXP eliminates this fragmentation permanently.

---

## The Solution

BXP defines:

- A hierarchical file system architecture for organizing all
  air exposure data (the BXP volume)
- A structured, versioned file format (.bxp) for encoding
  individual exposure records
- A complete schema for every major pollutant, biological agent,
  and environmental variable
- A five-stage protocol: Locate → Detect → Interpret → Protect → Report
- An open REST API specification for reading, writing, and
  querying BXP data
- A security and privacy framework for protecting individual
  exposure records
- A governance model for maintaining and evolving the standard

---

## Why Software-Only Changes Everything

HTTP did not require you to build networking hardware.
PDF did not require you to build printers.
MP3 did not require you to build speakers.
SSL did not require you to build servers.

BXP does not require you to build sensors.

Any existing data source can write BXP-formatted data:
- Government air quality monitoring stations
- Satellite atmospheric data feeds
- Existing consumer sensor applications
- Phone-native sensors (temperature, humidity, pressure, camera)
- Community human observation reports
- Hospital and health system environmental records

BXP is the format layer. Everything else plugs into it.

---

## File System Architecture
```
BXP:/
├── /meta/           — volume metadata, index, checksums
├── /locations/      — geographic hierarchy using geohash
├── /agents/         — pollutant and biological agent definitions
├── /exposures/      — individual and aggregate exposure records
├── /devices/        — device registry and calibration data
├── /alerts/         — alert events and notifications
├── /community/      — community-submitted observations
├── /research/       — research-grade datasets
└── /system/         — system files, schema versions, audit logs
```

---

## The Five Protocol Stages

**Stage 1 — LOCATE**
Every BXP record is geographically contextualized using the
Geohash coordinate system. Minimum precision 5 (~5km cell).
Recommended precision 7 (~153m cell) for fixed sources.

**Stage 2 — DETECT**
Data enters BXP from any source — existing sensors, satellites,
government stations, phone-native sensors, or human observation.
No proprietary hardware required.

**Stage 3 — INTERPRET**
Raw data is normalized, quality-controlled, and translated into
the BXP canonical format with standardized units and WHO-aligned
health risk thresholds.

**Stage 4 — PROTECT**
BXP translates technical measurements into clear, standardized
risk levels — CLEAN through HAZARDOUS — with specific protective
actions for each level.

**Stage 5 — REPORT**
Individual observations contribute to collective intelligence.
One person's data point. One million people's data — a complete
map of the invisible.

---

## Agent Coverage

BXP v2.0 covers 30+ atmospheric agents including:

- Particulates: PM1, PM2.5, PM10, Black Carbon
- Gases: CO, CO2, NO2, NO, SO2, O3, H2S, NH3
- Volatile Organics: TVOC, Benzene, Formaldehyde, Toluene
- Biological: Mold Spores, Pollen, Bacteria, Dust Mite Allergen
- Heavy Metals: Lead, Mercury, Arsenic
- Environmental: Temperature, Humidity, Pressure, UV Index
- Derived Indices: US AQI, BXP Health Risk Index (BXP_HRI)

---

## BXP Health Risk Index

BXP_HRI is BXP's native composite health risk score (0–100).
Unlike single-pollutant indices, it incorporates all available
agents with WHO-derived weighting, exposure duration, and
population vulnerability modifiers.

| BXP Level  | BXP_HRI | Action Required                          |
|------------|---------|------------------------------------------|
| CLEAN      | 0–20    | No restrictions                          |
| MODERATE   | 21–40   | Sensitive groups monitor                 |
| ELEVATED   | 41–60   | Reduce heavy outdoor exertion            |
| HIGH       | 61–75   | N95 outdoors. Close windows.             |
| VERY HIGH  | 76–90   | Avoid outdoors. Air purifier indoors.    |
| HAZARDOUS  | 91–100  | Emergency level. Stay indoors.           |

---

## Security & Privacy

- Personal exposure records encrypted with AES-256-GCM by default
- Person identifiers stored as SHA-256 hashes only — never plain text
- All data in transit via TLS 1.3 minimum
- Ed25519 cryptographic signatures for data integrity
- Complete data deletion via single API call
- k-anonymized aggregates (minimum k=5 sources)
- Designed for GDPR and CCPA compliance from the ground up

---

## Compatibility

BXP is designed for compatibility with:

- US EPA Air Quality Index (AQI)
- WHO Air Quality Guidelines 2021
- HL7 FHIR (Patient exposure resources)
- OGC SensorThings API
- OpenAQ open data platform
- Schema.org / JSON-LD vocabulary

---

## Roadmap

| Version | Target      | Key Deliverables                                    |
|---------|-------------|-----------------------------------------------------|
| v1.0    | Feb 2026    | Original spec + Python implementation (FROZEN)      |
| v2.0    | Mar 2026    | Full file system + API + privacy framework           |
| v2.1    | Q2 2026     | SDKs: Python, JavaScript, Arduino, ESP32, mobile    |
| v3.0    | 2027        | Waterborne + soil extension, AI exposure forecasting|

---

## Full Specification

The complete BXP Technical Specification v2.0 is available in
[SPEC.md](SPEC.md).

It covers the full file system architecture, binary file format,
complete agent schema with WHO thresholds, REST API specification,
device integration standard, security framework, governance model,
and implementation guide.

---

## Contributing

BXP is an open standard governed by the BXP Foundation.

All contributions are welcome — specification improvements,
reference implementations, SDK development, documentation,
and translations.

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.
Open an issue to start a discussion.

---

## Origin

BXP was conceived and first implemented by Elvarin on
February 15, 2026. The original v1 specification and working
Python implementation established the core concepts:
user-owned data, offline-first architecture, SHA-256
verification, and the portable .bxp container format.

This repository continues that work as the official
BXP v2.0 specification and beyond.

---

## License

Copyright 2026 Elvarin

Licensed under the Apache License, Version 2.0.
You may not use this work except in compliance with the License.

http://www.apache.org/licenses/LICENSE-2.0

[![BXP on Product Hunt](https://api.producthunt.com/widgets/embed-image/v1/featured.svg?post_id=1090206&theme=dark)](https://www.producthunt.com/products/bxp-breathe-exposure-protocol)

---

*The air is public. The data should be too.*
