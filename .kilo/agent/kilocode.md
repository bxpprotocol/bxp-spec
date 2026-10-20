# Kilo Agent: BXP Protocol

You are working on the BXP (Breathe Exposure Protocol) repository — an open standard for atmospheric exposure data.

## Repository Context

- **Spec**: `SPEC.md` (v2.0, frozen wire format, 17 conformance vectors)
- **SDKs**: Python (`sdk/python/`), TypeScript (`sdk/typescript/`)
- **Reference server**: `reference-server/` (FastAPI)
- **Autonomous agents**: `.bxp/` (sentinel, ingest, scout)

## Guidelines

1. **Always read SPEC.md before proposing changes** — the spec is frozen for v2.x; breaking changes require MAJOR version + 18-month notice.
2. **Validate all .bxp files** — use `validate_bxp_record()` from the SDK; conformance vectors must pass.
3. **Never modify external repositories** — the scout agent is read-only; human review required for any external PR.
4. **Follow Conventional Commits** — `feat(scope):`, `fix(scope):`, `docs(scope):`, `chore(scope):`, `rfc(scope):`.
5. **Run `make check` before committing** — lint + typecheck + tests + conformance.

## Available Commands

- `make install` — Install dependencies
- `make check` — Full validation (lint, typecheck, tests, conformance)
- `make lint` — ruff check
- `make test` — pytest suite
- `make run` — Start reference server on localhost:5000
