# BXP Changelog

All notable changes to the Breathe Exposure Protocol are documented
in this file. The format follows [Keep a Changelog](https://keepachangelog.com)
and this project adheres to [Semantic Versioning](https://semver.org).

---

## [Unreleased]

_Nothing yet. The next release will appear here._

---

## [2.1.0] — 2026-10-03
### Reference node hardening (checkpoint 07)

Breaking: `GET /bxp/v2/sync` now takes `since` and returns `nextCursor`
(previously `sinceTs` / `nextSinceTs`). `since=0` still means "from the start".

- **Sync cursor is an ingest sequence, not a timestamp.** The old timestamp
  cursor let one far-future reading stall replication forever and skipped
  readings that arrived late from offline devices.
- **Deletion is real and replicates.** Deleting a reading erases its content
  (`secure_delete` on) and leaves a tombstone that `/sync` delivers, so peers
  erase their copies too. Previously only a flag was set.
- **Ownership.** Registering an existing device UUID is now 409 (it used to
  mint a new token for it). Anonymous callers cannot submit under a registered
  device's UUID, and an authenticated device cannot submit as another (403).
- **No silent overwrites.** Readings are insert-if-absent; a resubmission can
  no longer replace or resurrect a reading. Batches are stored atomically.
  Reading IDs now include location and values, so distinct readings at one
  instant no longer collide.
- **Privacy floor enforced.** Anonymous submissions and community reports are
  snapped to their geohash-5 cell centre (SPEC.md 9.1); exact coordinates were
  previously stored and returned.
- **`/nearby` correctness.** The 3x3 geohash block is chosen from the search
  radius and latitude; a fixed precision-5 block missed readings well inside
  the radius at high latitude. Queries are also index-friendly now (range
  predicates instead of `LIKE`).
- **Pagination.** The `agent` filter runs in SQL, so `total`, `limit` and
  `offset` agree. Limits are validated (422) instead of silently trusted.
- **Ingest keeps what clients send.** Agent-level fields (`uncertainty`,
  `method`, the SPEC.md 5.5.1 `correction` object) and top-level `ext` /
  `context` survive storage and replication (SPEC.md 5.7).
- **Input bounds.** NaN/Infinity rejected; batch size, string lengths,
  timestamps and identifiers are capped. The city cache is bounded.
- **HTML/JS injection.** The dashboard, widget, map and compare pages escape
  every value that comes from the URL or the upstream API; the city name is
  URL-encoded when calling AQICN.
- `POST /nodes/announce` validates input, requires an http(s) URL, and cannot
  re-point an existing `nodeId`. `/metrics` labels are sanitised.
- Code layout: `server.py` split into `hri.py`, `pages.py`, `geo.py`;
  three duplicated geohash implementations replaced by `geo.py`.
- Tests: `test_database.py`, `test_pages.py`, `test_hri.py` (stdlib only) and
  about 25 new server tests. **The FastAPI routes and `test_server.py` were
  written without being run (no network to install FastAPI in the sandbox);
  run `make check` before relying on this.**

### Security

- **Broken access control (fixed):** `DELETE /bxp/v2/readings/{id}` only
  checked that the caller held *a* valid device token, not that it owned the
  reading, so any registered device could delete any other device's data.
  Now returns 403 unless the token's device submitted the reading.
- **Decompression bomb / DoS (fixed):** the binary decoder inflated gzip
  payloads without a size limit; a ~200 KB upload to the unauthenticated
  `POST /bxp/v2/readings` forced ~460 MB of allocation. Inflation is now
  capped at 16 MiB (`MAX_DECOMPRESSED_BYTES`) in both the Python and
  TypeScript decoders. (The first TypeScript version of this guard leaked an
  unhandled `AbortError` that would crash a Node process; fixed and tested.)
- **Unbounded request bodies (fixed):** uploads were read fully into memory.
  Now capped (default 8 MiB, `BXP_MAX_BODY_BYTES`), enforced for both
  declared and chunked bodies (413).
- **Rate-limit bypass (fixed):** `X-Forwarded-For` was trusted
  unconditionally, so any client could dodge per-IP limits by spoofing it.
  Ignored unless `BXP_TRUST_PROXY_HEADERS=true`.
- **Memory growth (fixed):** the rate limiter never evicted idle keys;
  combined with the spoofable header this was an unbounded-memory vector.
  Stale keys are now swept.
- `BXP_NODE_SYNC_TOKEN` is compared in constant time (`hmac.compare_digest`).
- **Vulnerable dependencies (fixed):** the pinned `fastapi==0.110.0` pulled
  `starlette 0.36.3` (14 known advisories per `pip-audit`). Upgraded to
  fastapi 0.141.1 / starlette 1.7.0 / uvicorn 0.54.0 / pydantic 2.13.5 /
  httpx 0.28.1; the full suite passes and `pip-audit` / `npm audit` are clean.

### Fixed

- **Docker image could not build** (`COPY spec/` referenced a directory that
  does not exist) and mounted its data volume over the application code, so
  upgrading the image kept running stale code. Data now lives in `/data`
  (new `BXP_DB_PATH`), the container runs as a non-root user, and the
  healthcheck no longer needs `curl`. *(The Dockerfile change is verified only
  by inspection and by running the same server outside Docker; Docker was not
  available in the development sandbox — CI now builds and probes the image.)*
- **Python SDK could not be built or installed** (invalid build backend, empty
  package discovery for single-file modules, README outside the package,
  console script pointing at a nonexistent module). Wheel now builds and
  imports from a clean virtualenv. Supported Python range corrected to >=3.10
  (what CI actually tests).
- **TypeScript SDK could not be built or tested via npm:** `npm test` ran Jest
  with no configuration, `npm run build` needed a missing Rollup config, and
  `package.json` exported files that were never produced. Now `tsc`-only, ESM,
  `npm test` runs the built-in Node test runner; dead Jest/Rollup dependencies
  removed. The package entry point now also exports the binary codec, which
  was previously unreachable for installed users.
- README/docs used port 8000 in 22 examples; the server, image, SDKs, CLI and
  Postman collection all use 5000. Fixed a nonexistent
  `pip install -r requirements.txt` path in the Quick Start.
- 22 lint findings (unused imports, empty f-strings).

### Added

- `GET /bxp/v2/nearby` and `GET /bxp/v2/sync` (spec §7 Stages 6-7); 12 tests.
- CI now runs lint, all Python suites on 3.10-3.12, TypeScript typecheck /
  tests / conformance / build, the wheel build+install, a Docker build+health
  probe, and dependency audits. Least-privilege permissions, concurrency
  cancellation, Dependabot for pip/npm/actions/docker.
- `SECURITY.md`, `Makefile` (`make check` = everything CI runs except
  Docker), `ruff.toml`, `requirements-dev.txt`, `sdk/python/README.md`, a
  Development Setup section in CONTRIBUTING, and complete `.env.example`.
- 13 new regression tests for the fixes above (ownership, rate limiter,
  proxy header, bomb, body cap, hostile-input fuzz).


### Added — Federation & discovery: `/nearby` and `/sync` (spec §7 Stages 6–7)

- **`GET /bxp/v2/nearby`** (§8.2.1) — "closest useful observation" lookup
  for a caller with no sensor of their own. Candidates are found via
  geohash-5 + 8-neighbor cell expansion (always covers a ~4.9km radius),
  filtered by true haversine distance, `maxAgeS`, an optional `agent`
  filter, and `minQuality` (INVALID always excluded regardless), then
  ranked by a blend of distance/freshness/quality — deliberately not a
  frozen formula per spec (`database.py::get_nearby_readings`).
- **`GET /bxp/v2/sync`** (§8.2.2) — pull-based federation replication:
  everything after an opaque `since` cursor, each reading carrying
  its originating `nodeId`, plus a `nextCursor`. (Originally a
  timestamp watermark; replaced, see "Reference node hardening" above.) Gated by a new
  `BXP_NODE_SYNC_TOKEN` env var if set — an explicit placeholder for the
  node trust/identity system spec §7 defers to a future RFC, not that
  system itself (same honesty pattern as the binary format's
  unimplemented encryption flag).
- 12 new server tests (7 nearby, 5 sync) covering distance/age/agent/
  quality filtering, ranking order, limit capping, and the token gate.
  **55/55 server tests passing**, no regressions.
- Corrected README.md's status table, roadmap, and Limitations section,
  which still said `/nearby` and `/sync` were "specified but not
  implemented" — they were the two items explicitly left over from the
  previous checkpoint's status report.

### Added — Conformance, TypeScript native format, calibration/trust, OpenAQ bridge

This round focused on two things: (1) making `.bxp` actually
interoperable across independent implementations rather than a
Python-only format with a JSON-only TypeScript SDK, and (2)
reprioritizing toward calibration/trust and bridging existing air
quality data sources, based on the current real-world context —
government reference-monitor funding is being cut in several
countries while low-cost sensor networks (PurpleAir, AfriqAir, OpenAQ)
are the fastest-growing source of coverage. See SPEC.md §3.7 and §7
Stage 2 for the reasoning.

- **Conformance model & spec/implementation reconciliation (SPEC.md)**
  - New §3.7 explicitly separates *normative* interoperability
    surface (record schema, binary encoding, verification,
    versioning) from *informative* recommendations. §4's "BXP Volume
    file system" is renamed "Recommended Node Storage Layout
    (informative, non-normative)" — it was previously written in
    normative-sounding language that conflicted with `.bxp` being a
    single-record portable format, not a filesystem/database.
  - New §5.7–§5.10: unknown/future-field handling (ignore-and-preserve),
    MAJOR/MINOR version negotiation rules, an `ext` extension
    namespace, and an explicit statement that encryption (flag bit1)
    is reserved but unspecified.
  - New §5.5.1 Calibration & Correction: an optional per-agent
    `correction` object (`applied`, `rawValue`, `model`,
    `referenceDeviceUuid`) so a corrected value never silently
    replaces the raw sensor output, plus a rule that `quality.flag:
    VALIDATED` must be backed by either an applied correction or an
    explicit `qcMethod` — not asserted on its own.
  - §8.2's REST endpoint table reconciled against the actual
    `reference-server/` implementation, which had drifted from it
    (e.g. spec said `/locations/{geohash}/current`, server implements
    `/bxp/v2/locations/{geohash}/latest`). Unimplemented-but-planned
    endpoints are now explicitly marked "Planned" instead of
    misrepresented as done.
  - New §7 Stage 6 (DISCOVER) and Stage 7 (FEDERATE), and new §15
    Conformance & Test Vectors, specifying the `/nearby` and `/sync`
    endpoints and the conformance-vector methodology below. (`/nearby`
    and `/sync` are specified but not yet implemented in
    `reference-server/` — see Unreleased/Next below.)

- **Cross-implementation conformance suite** (`conformance/`)
  - 17 golden `.bxp` vectors: 9 valid records covering every file
    type and flag combination, plus 6 deliberately malformed files
    (bad magic, truncated header, truncated payload, corrupted header
    checksum, corrupted payload checksum, corrupted payload byte) and
    an unsupported-major-version case.
  - `generate_vectors.py` (reproducible generator), `manifest.json`,
    `verify_python.py`, `verify_typescript.mjs`. All three currently
    pass — this is verified evidence that Python and TypeScript agree
    byte-for-byte on the native binary format.

- **TypeScript native binary `.bxp` support** (`sdk/typescript/bxp-binary.ts`)
  — did not exist before; the TS SDK only spoke JSON, so Python and
  TypeScript implementations could not actually exchange `.bxp` files.
  Mirrors `bxp_binary.py` field-for-field, including the new
  major-version rejection policy. 19 tests
  (`sdk/typescript/tests/bxp-binary.test.ts`) using Node's built-in
  test runner — zero new dependencies, runnable as `node --test
  tests/bxp-binary.test.ts` with nothing but Node 22+.

- **`bxp_binary.py`**: `decode_bxp_binary()` now actually enforces the
  MAJOR-version rejection rule (SPEC.md §5.8) when `verify=True` — it
  previously decoded any major version without checking. New
  `SUPPORTED_MAJOR` constant and `majorVersionSupported` field on the
  decode result.

- **`bxp_sdk.py`**
  - `validate_bxp_record()`: enforces the new VALIDATED-justification
    rule (§5.5.1) as a warning; fixed the version check to only flag a
    true major-version mismatch as an error, instead of warning on
    *any* non-"2.0" string (which incorrectly flagged valid future
    minor versions per §5.8).
  - `_build_bxp_record()`: fixed two real bugs found while adding test
    coverage — (1) agent entries supplied directly via the `agents`
    key skipped negative-value/missing-value validation (only the
    shorthand keys like `pm25=` were checked); (2) the builder
    aliased the caller's agent dicts instead of copying them, so
    mutating `record["agents"][0]` after the fact silently mutated
    the caller's original input too.
  - New `BXPClient.submit_record()`: submits an already-fully-built
    record as-is (original `deviceUuid`, `timestampUs`, `quality`,
    etc.), unlike `submit()` which always uses "now" and the client's
    own device UUID — needed by any importer/bridge handling
    historical or third-party data.
  - New `sdk/python/tests/test_bxp_sdk.py` (14 tests) — this file did
    not exist before; only the binary format had coverage.

- **OpenAQ → BXP importer** (`integrations/openaq_import.py`) —
  converts OpenAQ v3 API data into valid BXP records rather than
  requiring new hardware adoption before BXP has any real data in it.
  Deliberately conservative on trust: only marks a reading
  `VALIDATED` when OpenAQ's own metadata says the source is a
  reference-grade monitor (`isMonitor: true`); everything else comes
  through `UNVALIDATED`, per §5.5.1 — importing a feed does not
  launder its accuracy. 8 tests
  (`integrations/tests/test_openaq_import.py`) against an offline
  fixture; the live HTTP path could not be exercised against the real
  API in this sandbox (no outbound network access) and should be
  confirmed by a developer with network access before production use.

### Fixed

- See `_build_bxp_record()` bug fixes above (negative-value
  validation bypass, agent-dict aliasing) and the `bxp_binary.py`
  major-version enforcement gap above.



- **Binary `.bxp` container format** (spec §5.1–5.2), previously specified
  but not implemented:
  - `sdk/python/bxp_binary.py` — `encode_bxp_binary()` / `decode_bxp_binary()`
    implementing the exact 32-byte header (magic number, version, file type,
    flags, microsecond timestamp, payload length, header CRC32, payload
    CRC32), optional gzip payload compression, and tamper/corruption
    detection via checksums. Encryption (flag bit1) is deliberately left
    unimplemented — SPEC.md does not yet pin down a cipher/key-exchange —
    and raises `NotImplementedError` rather than silently no-op'ing.
  - `write_bxp_binary()` / `read_bxp_binary()` / `validate_bxp_binary()`
    added to `bxp_sdk.py`, sharing the same record-construction and
    validation logic as the JSON path so both representations stay
    semantically identical (spec's lossless-conversion requirement).
  - CLI: `bxp generate --binary [--compress]`; `bxp read` / `bxp validate`
    now auto-detect binary vs JSON by magic bytes; new `bxp convert`
    command converts either direction.
  - 31 unit tests in `sdk/python/tests/test_bxp_binary.py` covering header
    layout, all six file-type codes, flags, round-trip losslessness,
    checksum/tamper detection, and file-based conversion helpers.

### Fixed

- CLI: `cmd_generate` / `cmd_read` crashed when displaying the HRI advice
  line (`ValueError: not enough values to unpack`) — `RISK_LEVELS` tuples
  have 5 fields, not the 6 the unpacking assumed. Every `bxp generate` and
  `bxp read` call hit this.
- CLI: `bxp generate --lat 0 --lon 0` silently dropped both coordinates
  because of a falsy (`if args.lat:`) check instead of `is not None`.

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
