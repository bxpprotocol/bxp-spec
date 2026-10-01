# Security Policy

## Reporting a Vulnerability

**Please DO NOT open a public issue** for security problems.

Report privately using either:

- **GitHub Security Advisories**: Use the **"Report a vulnerability"** button on this repository's *Security* tab (private vulnerability reporting)
- **Email**: **bxpprotocol@proton.me** with subject `BXP security`

Include:
- What you found (type of vulnerability)
- How to reproduce it (steps, code, payload)
- Affected version/commit/branch
- Potential impact assessment
- Whether you want public credit (we will credit reporters who want credit)

This is a volunteer-run research project: reports are handled on a best-effort basis. We aim to acknowledge within 72 hours and provide a fix timeline within 7 days.

---

## Scope

**In scope** (this repository):
- Reference server (`reference-server/server.py`, `reference-server/database.py`)
- Python SDK (`sdk/python/bxp_sdk.py`, `sdk/python/bxp_binary.py`)
- TypeScript SDK (`sdk/typescript/bxp-sdk.ts`, `sdk/typescript/bxp-binary.ts`)
- CLI tool (`cli/bxp_cli.py`)
- Integrations (`integrations/mqtt_bridge.py`, `integrations/openaq_import.py`)
- Binary `.bxp` parsers (both Python and TypeScript)
- Conformance test infrastructure

**Out of scope:**
- Third-party implementations (even if listed in docs)
- User-deployed infrastructure (Docker, reverse proxies, TLS termination)
- External APIs (OpenAQ, AQICN, PurpleAir, etc.)

---

## Critical Attack Surfaces

### Binary `.bxp` Parsers (Highest Priority)
Both Python (`bxp_binary.py`) and TypeScript (`bxp-binary.ts`) consume untrusted bytes directly.

**Must guarantee:**
- Malformed input → clean error, **never** crash, OOB read, or infinite loop
- Decompression bombs → rejected before inflation (current: 10MB limit)
- CRC32 validation → mandatory on decode, never skipped
- Header bounds → strictly enforced (32-byte fixed header)
- Payload length → matches declared length exactly
- Version negotiation → unsupported major rejected, minor accepted per spec

### Reference Server (FastAPI)
- **Input validation**: All endpoints use Pydantic models — validate at boundary
- **Rate limiting**: In-memory, per-process. `X-Forwarded-For` ignored unless `BXP_TRUST_PROXY_HEADERS=true` (enable ONLY behind trusted proxy)
- **Authentication**: 
  - Device registration: open, rate-limited (5/min/IP)
  - Node sync (`/sync`): shared secret (`BXP_NODE_SYNC_TOKEN`) — placeholder, real trust deferred to RFC
  - No JWT/OAuth yet — planned for v2.1
- **SQL injection**: All queries parameterized (ruff S608 false positives suppressed in `database.py`)

### CLI Tool
- File I/O: validates all inputs, no arbitrary code execution
- Network: uses `requests` with timeout defaults
- Subprocess: none used

---

## Known, Documented Security Posture (Not Vulnerabilities)

These are **deliberate limitations** of a reference implementation; see [README "Limitations"](README.md#limitations) and `SPEC.md`:

| Limitation | Status | Mitigation |
|------------|--------|------------|
| Device registration open | Known | Rate-limited 5/min/IP; production deployments SHOULD add auth |
| `/sync` shared secret only | Known | Set `BXP_NODE_SYNC_TOKEN` env var; real node trust in future RFC |
| Rate limiting in-memory | Known | Not distributed; use external rate limiter (nginx, Cloudflare) in production |
| `X-Forwarded-For` ignored by default | Known | Enable `BXP_TRUST_PROXY_HEADERS=true` ONLY behind trusted proxy |
| Binary encryption flag reserved, not implemented | Spec-defined | Encoder refuses rather than pretending (SPEC §4.1 flag bit 1) |
| BXP-HRI not clinically validated | Known | Labeled "experimental" everywhere; not for medical use |
| No TLS in reference server | Known | Terminate TLS at reverse proxy (nginx, Caddy, Cloudflare) |
| No audit logging | Known | Add structured logging in production deployment |

---

## Dependency Security

We run automated dependency audits in CI:

```bash
# Python
pip-audit -r reference-server/requirements.txt --desc on

# Node.js
cd sdk/typescript && npm audit --audit-level=high
```

**Policy:**
- Critical/High CVEs → patch within 7 days of disclosure
- Medium CVEs → patch in next minor release
- Low CVEs → patch when convenient
- Zero-day in transitive deps → assess exploitability, mitigate if feasible

---

## Secure Deployment Checklist

For production deployments of the reference server:

- [ ] Terminate TLS at reverse proxy (Caddy, nginx, Cloudflare)
- [ ] Set `BXP_NODE_SYNC_TOKEN` to strong random secret (32+ chars)
- [ ] Set `BXP_TRUST_PROXY_HEADERS=true` ONLY behind trusted proxy
- [ ] Configure external rate limiting (nginx `limit_req`, Cloudflare WAF)
- [ ] Enable structured JSON logging + log aggregation
- [ ] Set up health check monitoring (`/bxp/v2/health`)
- [ ] Run behind WAF with OWASP Core Rule Set
- [ ] Regular dependency updates (`pip-audit`, `npm audit`)
- [ ] Backup SQLite database with encryption at rest
- [ ] Network segmentation: node on private network, proxy in DMZ

---

## Supported Versions

| Version | Status | Support |
|---------|--------|---------|
| Latest release / `main` | ✅ Active | Security fixes |
| Previous major (v1.x) | ❌ EOL | None |

Only the latest release and `main` branch receive security fixes. Upgrade promptly.

---

## Disclosure Timeline

1. **Report received** → Acknowledge within 72 hours
2. **Assessment** → Confirm validity, assess severity (CVSS)
3. **Fix development** → Target: Critical 7 days, High 14 days, Medium 30 days
4. **Testing** → Full test suite + conformance + regression tests
5. **Release** → Patch version, security advisory published
6. **Credit** → Reporter credited in release notes (if desired)

---

## Contact

- **Security email**: bxpprotocol@proton.me (PGP key available on request)
- **GitHub Security**: https://github.com/bxpprotocol/bxp-spec/security/advisories
- **Maintainer**: Elvarin (ORCID: 0009-0001-4856-4986)

---

*Security is a shared responsibility. If you deploy BXP in production, you own the operational security of your deployment.*