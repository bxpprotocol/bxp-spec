# BXP Agent Instructions

This file provides guidance for AI agents (including Kilo) working on the BXP Protocol repository.

## Repository Overview

BXP (Breathe Exposure Protocol) is an open, universal data standard for atmospheric exposure data — like HTTP for air quality.

- **Spec**: `SPEC.md` (v2.0, frozen wire format)
- **Reference server**: `reference-server/` (FastAPI, SQLite)
- **Python SDK**: `sdk/python/bxp_sdk.py`, `sdk/python/bxp_binary.py`
- **TypeScript SDK**: `sdk/typescript/`
- **CLI**: `cli/bxp_cli.py` (shim to `sdk/python/bxp_cli.py`)
- **Integrations**: `integrations/` (MQTT bridge, OpenAQ importer)
- **Conformance**: `conformance/` (17 golden vectors)
- **Website**: `bxpprotocol.github.io` (separate repo)
- **Autonomous agents**: `.bxp/` (sentinel, ingest, scout)

## Key Rules for Agents

### 1. Never modify external repositories
The BXP Integration Scout (`bxp-scout`) is read-only. It discovers and scores projects but never opens PRs or issues to external repos. Human review is required before any external contribution.

### 2. Spec compliance is non-negotiable
All `.bxp.json` and `.bxp` files must validate against `SPEC.md v2.0`. The SDK's `validate_bxp_record()` is the source of truth. Conformance vectors in `conformance/` must pass.

### 3. Conventional Commits
Commit messages must follow Conventional Commits:
```
feat(scope): description
fix(scope): description
docs(scope): description
chore(scope): description
rfc(scope): description
```

### 4. Make targets
- `make install` — Install dev dependencies
- `make check` — Lint + typecheck + tests + conformance
- `make lint` — ruff check
- `make test` — pytest
- `make run` — Start reference server

### 5. Branch naming
- `feat/...` — New features
- `fix/...` — Bug fixes
- `docs/...` — Documentation
- `chore/...` — Maintenance
- `rfc/...` — Specification changes

### 6. Autonomous agent files (`.bxp/`)
Files under `.bxp/` are managed by autonomous agents (sentinel, ingest, scout). Do not edit manually unless fixing a bug. Each agent writes its own state/reports there.

## Project Structure

```
bxp-spec/
├── SPEC.md                 # Protocol specification v2.0
├── README.md               # Project overview
├── CONTRIBUTING.md         # Contribution guide
├── GOVERNANCE.md           # Governance model
├── SECURITY.md             # Security policy
├── CODE_OF_CONDUCT.md      # Community standards
├── CHANGELOG.md            # Release history
├── CITATION.cff            # Citation metadata
├── .bxp/                   # Autonomous agent code (sentinel, ingest, scout)
├── cli/                    # CLI tool
├── conformance/            # Test vectors (17 golden files)
├── datasets/               # Sample .bxp.json data
├── docs/                   # API, developer, protocol docs
├── examples/               # Usage examples
├── integrations/           # MQTT bridge, OpenAQ importer
├── reference-server/       # FastAPI reference node
├── sdk/                    # Python + TypeScript SDKs
├── scripts/                # Build and check scripts
├── .github/workflows/      # CI/CD pipelines
└── pyproject.toml          # Python packaging
```

## Testing

- Python tests: `reference-server/tests/`, `sdk/python/tests/`, `integrations/`
- TypeScript tests: `sdk/typescript/` (npm test)
- Conformance: `python conformance/verify_python.py && node conformance/verify_typescript.mjs`
- All tests must pass before PR merge

## Contact

- Issues: https://github.com/bxpprotocol/bxp-spec/issues
- Discussions: https://github.com/bxpprotocol/bxp-spec/discussions
- Email: bxpprotocol@proton.me
