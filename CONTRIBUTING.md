# Contributing to BXP Protocol

Thank you for your interest in contributing to the Breathe Exposure Protocol. BXP is an open universal standard for atmospheric exposure data interoperability — Apache 2.0 licensed, no gatekeepers.

---

## Quick Start

```bash
# Clone and setup
git clone https://github.com/bxpprotocol/bxp-spec.git
cd bxp-spec
make install       # Python + TypeScript dev dependencies
make check         # lint + typecheck + all tests + conformance vectors
make run           # start local node on http://localhost:5000
```

`make check` mirrors CI. Individual targets: `lint`, `typecheck`, `test`, `conformance`.

---

## Ways to Contribute

### 🐛 Report a Bug
Use the **[Bug Report template](.github/ISSUE_TEMPLATE/bug_report.yml)** — includes structured fields for component, version, reproduction steps, and environment.

### ✨ Request a Feature
Use the **[Feature Request template](.github/ISSUE_TEMPLATE/feature_request.yml)** — describes the problem, proposed solution, alternatives, and priority.

### 📋 Propose a Specification Change (RFC)
Use the **[RFC Proposal template](.github/ISSUE_TEMPLATE/rfc_proposal.yml)** — formal 30-day public comment process per SPEC.md §12.3. All spec changes require RFC.

### 🔧 Submit Code
1. Fork → branch → changes → PR
2. Fill the **[PR Template](.github/PULL_REQUEST_TEMPLATE.md)** completely
3. Ensure `make check` passes locally
4. Reference related issue(s)

**Code standards:**
- Python: `ruff` (line-length 100, py39 target)
- TypeScript: `tsc --noEmit` + project style
- Tests required for new functionality
- Conformance vectors updated for wire format changes

---

## High-Impact Contributions Needed

| Area | Description | Effort |
|------|-------------|--------|
| **Embedded C/ESP32/Arduino codec** | Native binary `.bxp` encoder/decoder for microcontrollers | High |
| **PurpleAir importer** | Real-time import from PurpleAir API → valid BXP records | Medium |
| **Rust SDK** | Independent implementation for conformance validation | High |
| **Mobile SDKs** | React Native, Flutter, Kotlin/Swift | High |
| **Load testing** | Reference server benchmarking, optimization | Medium |
| **Documentation translations** | ES, FR, ZH, AR, HI, PT, SW, etc. | Low-Medium |

See [Roadmap](README.md#roadmap) for full list.

---

## RFC Process (Specification Changes)

All specification changes follow the formal RFC process:

1. **Open RFC Issue** using the template with `rfc` label
2. **30-day public comment** — community discusses
3. **Maintainer decision** — accept, reject, or request revision
4. **Implementation** — accepted RFCs → next appropriate version
5. **Conformance update** — new test vectors for wire format changes

See [SPEC.md §12.3](SPEC.md#123-rfc-process) and [GOVERNANCE.md](GOVERNANCE.md#rfc-process-documented-not-yet-used) for full details.

---

## Development Guidelines

### Specification Changes
- Use RFC 2119 keywords (MUST, SHOULD, MAY, MUST NOT)
- New fields are OPTIONAL by default (SPEC §5.7 extensibility)
- Breaking changes require MAJOR version, 18-month notice, dual-version support
- All new agents need WHO/equivalent threshold data

### Code Quality
| Language | Linter | Test Command |
|----------|--------|--------------|
| Python | `ruff check .` | `python -m pytest` |
| TypeScript | `tsc --noEmit` | `npm test` (in sdk/typescript) |
| Conformance | — | `python conformance/verify_python.py && node conformance/verify_typescript.mjs` |

### Commit Messages
Follow [Conventional Commits](https://www.conventionalcommits.org/):
```
feat(sdk): add PurpleAir importer module
fix(server): handle NaN in JSON payloads
docs(readme): update quick start with Docker
rfc(spec): add NOX composite agent (RFC-001)
```

---

## Review Process

| Change Type | Review Timeline | Reviewers |
|-------------|-----------------|-----------|
| Bug fixes, docs, clarifications | 7 days | Maintainer |
| New optional features (MINOR) | 30 days | Maintainer + community |
| Breaking changes (MAJOR) | 90 days minimum | Maintainer + RFC process |
| Security fixes | Immediate (private) | Maintainer (see SECURITY.md) |

---

## Community Standards

BXP is built on the principle that **clean air is a human right** — not a privilege of geography or wealth. Our community reflects that principle.

**We expect all contributors to:**
- Treat everyone with respect regardless of background or experience
- Give and receive feedback constructively
- Prioritize public good over personal/commercial interests
- Be honest about limitations, uncertainties, and trade-offs
- Credit others for their ideas and work

**Unacceptable behavior:**
- Harassment or discrimination of any kind
- Bad-faith contributions designed to harm the project
- Attempts to introduce proprietary dependencies or vendor lock-in
- Misrepresentation of the specification for commercial advantage

---

## Recognition

Every contributor is recognized:
- **CHANGELOG.md** — significant contributions credited by name
- **GitHub Contributors** — all contributors listed in repo insights
- **RFC authorship** — RFCs permanently attributed to authors
- **Implementation credits** — reference implementations credited to builders

---

## Getting Help

| Channel | Purpose |
|---------|---------|
| [GitHub Issues](https://github.com/bxpprotocol/bxp-spec/issues) | Specific technical questions, bugs, features |
| [GitHub Discussions](https://github.com/bxpprotocol/bxp-spec/discussions) | Open-ended conversation, ideas, Q&A |
| [Email](mailto:bxpprotocol@proton.me) | Partnership, institutional, security inquiries |

---

## First Time Contributing?

1. **Read SPEC.md** — the best first contribution is opening an issue for anything unclear
2. **Look for `good first issue` label** — scoped tasks for new contributors
3. **Run the validator** — try https://bxpprotocol.github.io/bxp-spec/validator.html in your browser
4. **Join Discussions** — introduce yourself and ask questions

---

*BXP is built by people who believe the air is public and the data about it should be too.*

**Copyright 2026 BXP Protocol Contributors — Apache 2.0 License**