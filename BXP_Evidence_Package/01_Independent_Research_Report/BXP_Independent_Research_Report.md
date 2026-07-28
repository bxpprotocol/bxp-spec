# Breathe Exposure Protocol (BXP)
## Independent Research into Interoperability for Digital Atmospheric Exposure Information

**Author:** Elvarin  
**Project inception:** February 15, 2026  
**Specification version:** BXP v2.0 (March 2026)  
**Implementation version:** Reference Server v2.1 (2026)  
**Repository:** https://github.com/bxpprotocol/bxp-spec  
**Specification DOI:** https://doi.org/10.5281/zenodo.18906812  
**Implementation DOI:** https://doi.org/10.5281/zenodo.18907003  
**ORCID:** https://orcid.org/0009-0001-4856-4986  
**License:** Apache 2.0

---

## Abstract

This report documents the independent research and technical development of the Breathe Exposure Protocol (BXP), an open data standard for atmospheric exposure information. Beginning with a personal observation about the fragmentation of air quality data, the investigation evolved through a series of conceptual and technical stages into a complete protocol specification, a working reference server implementation, a Python SDK, a command-line tool, and associated tooling. The central research question is: *Can a universal, open data standard eliminate the interoperability failures that prevent air quality information from being used to protect human health?* BXP proposes and partially demonstrates that such a standard is technically feasible, buildable independently, and practically deployable. This report is honest about the distinction between what has been designed, what has been implemented, and what remains proposed or future work.

---

## 1. Background and Motivation

### 1.1 The Original Question

The project began with a simple observation: air pollution monitoring data exists in enormous quantities — from government monitoring stations, consumer sensors, satellite instruments, mobile applications, and academic research programmes — yet the data cannot easily be used together. A sensor deployed in Accra cannot feed its readings to an application designed for Delhi. A researcher in London cannot query a database in Lagos using a single standard query format. A hospital in Nairobi cannot receive structured exposure data from a citizen's phone.

This is not a problem of data volume or sensor availability. Consumer-grade air quality sensors have become increasingly affordable, and monitoring infrastructure has expanded considerably across the Global South in the last decade. The barrier is not hardware. The barrier is data fragmentation.

### 1.2 The Problem in Context

Air pollution causes approximately 7 million premature deaths annually, according to the World Health Organization (WHO, 2021) — more than HIV, malaria, and tuberculosis combined. The communities most affected — in sub-Saharan Africa, South Asia, and parts of Latin America — are often the communities with the least access to structured air quality information, because their local monitoring data cannot interoperate with global systems.

The investigation identified four structural failures in the current ecosystem:

| Failure | Description |
|---------|-------------|
| Fragmentation | Every device manufacturer, government agency, and research institution uses incompatible data formats |
| Proprietary lock-in | Many existing standards are closed, expensive to license, or tied to specific hardware |
| Geographic inequality | Comprehensive monitoring infrastructure is concentrated in wealthier nations |
| No universal open standard | No freely available, community-governed protocol exists for atmospheric exposure data |

### 1.3 Why This Matters

The absence of a universal data standard is not merely a technical inconvenience. It creates a structural barrier to:

- Coordinated public health responses to air pollution events
- Cross-border research on transboundary pollution (e.g. Saharan dust events, industrial corridor monitoring)
- Integration of citizen sensor data with government and research datasets
- Development of applications that can serve diverse geographic contexts

---

## 2. Research Question and Initial Hypothesis

### 2.1 Research Question

*Is it possible to design an open, universal data standard for atmospheric exposure information that is technically complete, platform-independent, privacy-preserving, and freely implementable — and can such a standard be demonstrated through a working reference implementation?*

### 2.2 Initial Hypothesis

The initial hypothesis was that existing standards could be adapted for this purpose. Early investigation revealed that no existing open standard adequately covered the full scope of atmospheric exposure data (including biological agents, heavy metals, and volatile organic compounds), addressed privacy requirements for personal exposure data, or provided a federated architecture that preserved data sovereignty.

The hypothesis therefore shifted: a new protocol was needed, designed from first principles, with interoperability as a core design goal rather than an afterthought.

---

## 3. Investigation and Reasoning

### 3.1 The Interoperability Problem

The core insight that emerged from the investigation was that the problem of air quality data is not primarily a measurement problem or an analysis problem — it is an interoperability problem. The data exists. The sensors exist. What does not exist is a shared language.

This mirrors problems that have been solved in other domains through open standards:
- HTTP unified data transfer across the web
- MP3 and MP4 unified audio and video distribution
- PDF unified document representation across platforms
- DICOM unified medical imaging across hospitals

Each of these standards eliminated fragmentation not by forcing everyone to use the same hardware, but by defining a common data representation that any conforming system could read and write.

The analogy that emerged was: BXP should be to atmospheric exposure data what HTTP is to the web — a protocol, not a platform.

### 3.2 Existing Standards Analysis

Investigation of existing standards identified:

- **AQI (US EPA):** Single-country, single-scale index. Does not cover biological agents, volatile organic compounds, or heavy metals. Not designed as a data exchange format.
- **European CAQI:** Similar limitations to US AQI. Regional rather than universal.
- **OpenAQ:** A valuable data aggregation project, but not a protocol standard — it collects data, it does not define how data should be represented at source.
- **OGC SensorThings API:** A general IoT observation model that could theoretically be used for air quality, but lacks the domain-specific schema, health risk indexing, privacy architecture, and community reporting layers that atmospheric exposure data requires.
- **HL7 FHIR:** A healthcare data standard with observation resources that partially overlap, but is designed for clinical records rather than environmental monitoring.

None of these provided a complete, open, domain-specific protocol for the problem. This gap confirmed that a new standard was warranted.

### 3.3 Design Principles

The protocol design was guided by six principles, each chosen to address a specific failure mode in existing approaches:

1. **Universality** — must work for any data source, any platform, any geography, at any scale
2. **Interoperability** — any BXP-compliant system must be able to read any BXP-compliant file
3. **Openness** — no licensing fees, no closed sections, no gatekeepers
4. **Accessibility** — implementable on low-resource devices including basic smartphones
5. **Privacy-First** — individual exposure records private by default
6. **Extensibility** — must grow without breaking existing implementations

---

## 4. Technical Development

### 4.1 Protocol Design

The BXP protocol is organized around five conceptual stages that any atmospheric exposure data event must pass through:

- **Stage 1 — LOCATE:** Geographic contextualization using geohash encoding (minimum precision 5, approximately 4.9 km cell)
- **Stage 2 — DETECT:** Data source classification into three tiers, from phone-native sensors (Tier 1) to reference instruments (Tier 3)
- **Stage 3 — INTERPRET:** Automated quality control, unit normalization, and data validation
- **Stage 4 — PROTECT:** Health risk assessment using the BXP Health Risk Index (BXP_HRI)
- **Stage 5 — REPORT:** Community observation schema enabling qualitative human observations to be combined with quantitative sensor data

### 4.2 The BXP File Format

BXP defines two representations of the same data, designed to be losslessly convertible:

- **Binary `.bxp`:** A compact format with a 32-byte fixed header including magic number (`0x42585000`), version, file type, flags (compression, encryption, signature), timestamp, payload length, and CRC32 checksums. *The binary format specification is complete; a software implementation of the binary encoder/decoder has not yet been built.*
- **JSON `.bxp.json`:** A human-readable format semantically identical to the binary representation. *This format is fully implemented in the reference server, SDK, and CLI.*

### 4.3 The Agent Schema

BXP defines a canonical schema for 31 atmospheric agents across 7 categories:
- Particulates: PM1, PM2.5, PM10, Black Carbon
- Gaseous pollutants: CO, CO₂, NO₂, NO, SO₂, O₃, H₂S, NH₃
- Volatile organic compounds: TVOC, Benzene, Formaldehyde, Toluene, Xylene, Naphthalene
- Biological agents: Mold spores, Grass pollen, Tree pollen, Total bacteria, Dust mite allergen
- Heavy metals: Lead, Mercury, Arsenic
- Environmental variables: Temperature, Humidity, Pressure, UV Index
- Derived indices: AQI_US, BXP_HRI

All thresholds are aligned with WHO Air Quality Guidelines 2021 (WHO, 2021).

### 4.4 BXP Health Risk Index (BXP_HRI)

BXP_HRI is a composite health risk score on a 0–100 scale, designed to address a limitation of existing single-pollutant indices (such as US AQI): they measure one pollutant at a time, while actual health risk is a function of simultaneous exposure to multiple agents.

The BXP_HRI formula:

```
agent_risk(i) = min(1.0, value(i) / WHO_threshold(i))
raw_HRI = Σ ( agent_risk(i) × weight(i) )
BXP_HRI = min(100, raw_HRI × 100 × duration_factor × vulnerability_factor)
```

Agent weights are derived from WHO disability-adjusted life year (DALY) burden data, with PM2.5 weighted most heavily (0.35) due to its documented contribution to the highest share of air pollution deaths globally.

Six risk levels map BXP_HRI scores to actionable health guidance: CLEAN (0–20), MODERATE (21–40), ELEVATED (41–60), HIGH (61–75), VERY_HIGH (76–90), HAZARDOUS (91–100).

### 4.5 Reference Server Implementation

A complete reference server was built using FastAPI (Python), SQLite for persistence, and uvicorn as the ASGI server. The server implements:

- REST API with 20+ endpoints covering readings submission, retrieval, location-based queries, device registration, community reports, search, and federated node discovery
- Device token authentication with Bearer token validation
- Rate limiting (per-IP sliding window)
- Cryptographic integrity verification (SHA-256 payload hashes)
- Privacy controls: geohash precision floors, k-anonymity for aggregates (minimum k=5), cryptographic deletion with proof
- Real-time dashboard with interactive map (Leaflet.js), time-series charts (Chart.js), multi-city comparison, auto-refresh, and data export
- Prometheus metrics endpoint
- Embeddable widget endpoint

The server is functional and can be run locally or deployed. It connects to the AQICN real-time air quality API for live city data when configured with an API token; it operates in local-data-only mode without one.

### 4.6 Python SDK

The Python SDK (`bxp_sdk.py`) provides a complete programmatic interface to BXP, including:
- `write_bxp()` — create and sign `.bxp.json` files with integrity hashes
- `read_bxp()` — read and verify `.bxp.json` files
- `validate_bxp()` — validate files against the BXP v2.0 specification
- `calculate_risk()` — compute BXP_HRI with duration and population modifiers
- `BXPClient` — synchronous HTTP client for server interaction
- `AsyncBXPClient` — asynchronous HTTP client for use in async Python applications
- `OfflineQueue` — local queue that buffers readings when a server is unreachable and flushes when connectivity is restored

### 4.7 Command-Line Interface

The CLI (`bxp_cli.py`) provides a developer-oriented command-line interface supporting: `generate`, `read`, `validate`, `submit`, `batch-submit`, `export` (CSV, GeoJSON), `hri`, `server-status`, `map` (HTML generation), and `config`.

### 4.8 Supporting Artefacts

Additional project components include:
- TypeScript/JavaScript SDK (`sdk/typescript/bxp-sdk.ts`)
- MQTT bridge for IoT sensor integration (`integrations/mqtt_bridge.py`)
- Sample dataset of 10 global city readings (`datasets/sample_readings.bxp.json`)
- Docker and docker-compose configuration for one-command deployment
- Postman API collection for testing
- GitHub Actions CI workflow
- Complete protocol documentation (`SPEC.md`, `docs/`, `CHANGELOG.md`)

---

## 5. Findings and Observations

### 5.1 What Has Been Demonstrated

Through the development of BXP, the following has been demonstrated:

1. **A universal data format is technically feasible.** The `.bxp.json` format successfully encodes readings from any source — phone sensors, government data feeds, manual observation — in a single schema.

2. **A composite health risk index can be computed from multi-agent data.** BXP_HRI provides a single, interpretable score that incorporates all available agents simultaneously, with duration and population vulnerability modifiers.

3. **A privacy-preserving architecture can be implemented.** The reference server enforces geohash precision floors for personal records, k-anonymity for public aggregates, and cryptographic deletion.

4. **A minimal BXP node can be run by any developer.** The reference server installs in four Python packages and starts with a single command.

5. **The data format spans global contexts.** The sample dataset demonstrates BXP encoding readings from Accra, Lagos, Delhi, Beijing, London, São Paulo, New York, Nairobi, Jakarta, and Cairo in a single file — spanning all six inhabited continents.

### 5.2 Limitations

The following limitations are honestly acknowledged:

1. **The binary `.bxp` file format is specified but not yet implemented in software.** The 32-byte header and binary encoding schema are fully defined; a working encoder/decoder has not been built.

2. **The federated network protocol is aspirational.** The spec describes how BXP nodes should discover each other and exchange data. The reference server has a `/nodes` endpoint for node registration, but full peer-to-peer synchronisation between independent nodes has not been implemented.

3. **BXP_HRI has not been clinically or epidemiologically validated.** The weighting scheme is derived from WHO DALY burden data and WHO threshold values, but the index itself has not been reviewed by epidemiologists or validated against health outcome data.

4. **The reference server is a prototype, not a production system.** It has not been load-tested, security-audited, or deployed at scale.

5. **The BXP Foundation described in the governance section is aspirational.** No such organisation currently exists. The governance structure is proposed as a model for future development.

6. **The compatibility matrix lists standards against which BXP has not been formally reviewed.** Claimed compatibility with GDPR, FHIR, and OGC SensorThings API is based on design intent, not formal compliance assessment.

7. **No third-party implementations exist.** BXP has not been adopted by any external organisation. The reference implementation is the only working implementation.

---

## 6. Unresolved Questions

The following questions remain open for future research:

1. **Is the BXP_HRI weighting scheme epidemiologically defensible?** The weights are derived from WHO burden data, but their use in a composite index has not been validated against health outcomes.

2. **How should federated nodes handle conflicting data?** When two nodes have different readings for the same geohash and time window, what is the correct reconciliation approach?

3. **What geohash precision is appropriate for personal exposure tracking?** Precision 5 (~4.9 km) protects location privacy but may be insufficient for meaningful personal exposure assessment in complex urban environments.

4. **How can quality flags be made consistent across implementations?** The current QC rules are automated heuristics. A formal inter-rater reliability assessment would be needed to standardise quality flags across independent implementations.

5. **What governance model is most appropriate for an open protocol with a public health mission?** The proposed BXP Foundation model follows established open standards bodies, but whether this is the right approach remains an open question.

---

## 7. Future Research and Development

*These are proposed directions, not completed work.*

- Binary `.bxp` format implementation (encoder/decoder in Python and C)
- Arduino and ESP32 SDK implementations for IoT sensors
- BXP-STREAM real-time data extension
- Waterborne and soil contamination extension (v3.0)
- Epidemiological review of BXP_HRI weighting scheme
- Formal pilot deployment with a sensor network in a high-pollution city
- Engagement with an established environmental monitoring organisation for feedback on the specification
- HL7 FHIR R4 mapping documentation

---

## 8. Conclusion

BXP began with a simple observation about data fragmentation and evolved through independent investigation into a complete protocol specification and working reference implementation. The core technical problem — how to represent atmospheric exposure data in a universal, open, privacy-preserving format — has been addressed in the design, and the reference implementation demonstrates that the design is buildable.

The project is honest about what remains incomplete: the binary format is unimplemented, the federated network is aspirational, the index is unvalidated, and no third-party adoption has occurred. These are the natural limitations of independent research conducted by a single person over a short period.

What has been accomplished is the technical foundation: a complete open specification, a working reference server, a Python SDK, a command-line tool, a sample dataset, and a coherent design philosophy. The question of whether BXP — or something like it — could meaningfully address atmospheric data fragmentation at scale is one that requires broader engagement, external validation, and real-world deployment. This project establishes the conceptual and technical foundation for that next stage.

---

## References

World Health Organization. (2021). *WHO Global Air Quality Guidelines.* Geneva: World Health Organization. https://www.who.int/publications/i/item/9789240034228

Simcoe, T. (2012). Standard setting committees: Consensus governance for shared technology platforms. *American Economic Review, 102*(1), 305–336.

Berners-Lee, T., Fielding, R., & Frystyk, H. (1996). Hypertext Transfer Protocol — HTTP/1.0. *RFC 1945.* Internet Engineering Task Force.

OpenAQ. (2024). *OpenAQ Platform.* https://openaq.org

OGC SensorThings API. (2016). *OGC SensorThings API Part 1: Sensing.* Open Geospatial Consortium.

---

*Copyright 2026 Elvarin. Licensed under Apache 2.0.*  
*The air is public. The data should be too.*
