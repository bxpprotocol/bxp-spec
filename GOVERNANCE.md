# BXP Governance

## Project Identity

**BXP (Breathe Exposure Protocol)** is an open protocol for atmospheric exposure data interoperability.

- **Creator**: Elvarin (pseudonym)
- **Current Governance**: Single maintainer (Elvarin) — no formal foundation or committee exists yet
- **Legal Entity**: None yet. Apache 2.0 licensed code. No incorporated foundation, no trademark registration.
- **License**: Apache 2.0 — free to use, implement, modify, distribute
- **Domains**: `github.com/bxpprotocol` (GitHub org). `bxp-protocol.org` — not registered.
- **Trademarks**: None registered.
- **Contact**: bxpprotocol@proton.me (personal email), GitHub Issues (technical)

## Current Decision Authority

| Decision Type | Authority | Process |
|---------------|-----------|---------|
| Specification changes | Elvarin (maintainer) | RFC via GitHub Issues (30-day comment per CONTRIBUTING.md) |
| Reference implementation changes | Elvarin | PR review |
| Security issues | Elvarin | Private disclosure (SECURITY.md) |

**No formal governance structure exists yet.** The "Technical Steering Committee", "BXP Foundation", and "Advisory Board" described in SPEC.md §12 and CONTRIBUTING.md are **aspirational** — not yet formed.

## What Exists Today

- **Code**: Apache 2.0, public on GitHub
- **Spec**: SPEC.md v2.0 (frozen wire format, 17 conformance vectors)
- **RFC Process**: Documented in CONTRIBUTING.md §2 and SPEC.md §12.3 — not yet exercised
- **Bus Factor**: 1 (single maintainer)

## Planned Governance (Not Yet Implemented)

The following are **intentions**, not current reality:

1. **BXP Foundation** — Incorporate as non-profit open standards body
2. **Technical Steering Committee (TSC)** — 7 elected members from contributor community
3. **Working Groups** — Hardware, Software, Privacy, Health, Community
4. **Advisory Board** — WHO, agencies, manufacturers, academia, civil society
5. **Trademark Registration** — Defensive holding by Foundation
6. **Domain Registration** — bxp-protocol.org
7. **Financial Transparency** — Annual reports

## Succession & Continuity (Current Risk)

- Single maintainer holds GitHub org, email, domains (none registered)
- No formal succession plan
- Spec + conformance vectors archived on Zenodo (immutable DOIs)

## Funding

- None. Volunteer project. No grants, donations, or sponsorships received.

## RFC Process (Documented, Not Yet Used)

1. Submit RFC via GitHub Issue with `rfc` label
2. 30-day public comment period
3. Maintainer decides: accept, reject, or return for revision
4. Accepted RFCs → next appropriate version release

Full process: `CONTRIBUTING.md §2` and `SPEC.md §12.3`

## Versioning Policy

- MAJOR.MINOR.PATCH (semantic versioning)
- Breaking changes → MAJOR bump, 18-month advance notice, dual-version support
- New optional fields → MINOR bump, backward compatible
- Bug fixes/clarifications → PATCH

## Conformance

An implementation is "BXP 2.0 Compliant" iff it passes all 17 conformance vectors (Python + TypeScript reference implementations pass). Conformance vectors are frozen per major version.

## History

- v1.0: Internal draft (2024)
- v2.0: Public release with conformance model (2026-09) — **CURRENT STABLE**
- v2.1: Planned (SDK packaging, embedded codec)
- v3.0: Planned 2027 (water/soil, mesh, FHIR)

---

*This document reflects actual project state as of 2026-10. Aspirational items are explicitly marked. Changes follow the RFC process once governance exists.*