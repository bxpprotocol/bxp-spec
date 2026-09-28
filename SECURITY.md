# Security Policy

## Reporting a vulnerability

Please **do not open a public issue** for security problems.

Report privately using either:

- GitHub's **"Report a vulnerability"** button on this repository's
  *Security* tab (private vulnerability reporting), or
- email **bxpprotocol@proton.me** with the subject `BXP security`.

Include what you found, how to reproduce it, and the affected version/commit.
This is a volunteer-run research project: reports are handled on a best-effort
basis, and we will credit reporters who want credit.

## Scope

In scope: the reference server (`reference-server/`), the Python and
TypeScript SDKs, the binary `.bxp` parsers, the CLI, and the integrations.

The binary parsers deserve particular attention — they consume untrusted
bytes. Malformed input must be rejected with an error, never crash the
process or read out of bounds.

## Known, documented security posture (not vulnerabilities)

These are deliberate limitations of a reference implementation; see the
README "Limitations" section and `SPEC.md`:

- `POST /bxp/v2/devices/register` is open (rate-limited to 5/min per IP).
  Anyone can obtain a device token.
- `GET /bxp/v2/sync` "Node Token" is a single shared secret
  (`BXP_NODE_SYNC_TOKEN`); real inter-node trust is not yet specified.
  If the variable is unset, `/sync` is open.
- Rate limiting is in-memory and per-process. `X-Forwarded-For` is ignored
  unless `BXP_TRUST_PROXY_HEADERS=true`; enable that **only** behind a proxy
  that overwrites the header.
- Binary `.bxp` encryption (header flag bit 1) is specified but not
  implemented; the encoder refuses rather than pretending.
- BXP_HRI has no clinical validation and must not be used for medical decisions.

## Supported versions

Only the latest release / `main` receives fixes.
