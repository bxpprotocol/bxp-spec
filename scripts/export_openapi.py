#!/usr/bin/env python3
"""Export the reference node's OpenAPI contract to openapi.json and openapi.yaml.

The REST surface is the part of BXP other people integrate against, so the
contract has to be a committed artifact rather than something you have to
boot a server to discover. This script derives it from the FastAPI app so it
can never drift from the implementation.

    python scripts/export_openapi.py

Writes to the repository root:
    openapi.json   canonical, machine-readable
    openapi.yaml   same document, human-diffable

CI runs `make openapi-check` to fail if either file is stale.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "reference-server"))


def build() -> dict:
    import server  # noqa: E402  (import needs the sys.path entry above)

    spec = server.app.openapi()

    # The generated document is accurate but says nothing about who maintains
    # the contract or where to read prose documentation. Operators discover BXP
    # through API directories and code generators, which only ever see this
    # file, so the pointers have to live here.
    info = spec.setdefault("info", {})
    info.setdefault("title", "BXP Protocol REST API")
    info["summary"] = (
        "Open protocol for atmospheric exposure data. "
        "BXP is to air quality what HTTP is to the web."
    )
    info["description"] = (
        "This is the normative REST contract for a BXP v2.0 node.\n\n"
        "Every field, unit, enum, and error code is specified in the BXP "
        "specification. Implementations are expected to expose this contract "
        "unchanged so that any BXP client can query any BXP node.\n\n"
        "**Versioning.** MAJOR versions of the *protocol* are negotiated by the "
        "`major` path segment. MINOR additions are backward compatible and "
        "unknown response fields must be ignored-and-preserved "
        "(SPEC.md 5.7).\n\n"
        "**Conformance.** An implementation is BXP 2.0 compliant when it passes "
        "the golden-vector conformance suite, not merely when it serves these "
        "endpoints.\n\n"
        "**BXP-HRI is experimental.** The `bxpHri` field is a composite index "
        "weighted by WHO DALY data. It is not clinically or epidemiologically "
        "validated and must not be used for medical decisions."
    )
    info["version"] = "2.0"
    info["contact"] = {
        "name": "BXP Protocol contributors",
        "url": "https://github.com/bxpprotocol/bxp-spec",
        "email": "bxpprotocol@proton.me",
    }
    info["license"] = {
        "name": "Apache-2.0",
        "url": "https://www.apache.org/licenses/LICENSE-2.0",
        "identifier": "Apache-2.0",
    }
    info["termsOfService"] = "https://github.com/bxpprotocol/bxp-spec/blob/main/GOVERNANCE.md"

    ext = info.setdefault("externalDocs", {})
    ext["description"] = "BXP Protocol specification v2.0"
    ext["url"] = "https://github.com/bxpprotocol/bxp-spec/blob/main/SPEC.md"

    tags = [
        {"name": "Readings", "description": "Submit and query exposure observations."},
        {"name": "Locations", "description": "Geohash-scoped latest, history, and aggregate views."},
        {"name": "Discovery", "description": "Find relevant observations and readings near a point."},
        {"name": "Federation", "description": "Pull-based replication between independent nodes."},
        {"name": "Devices", "description": "Device registration and provenance."},
        {"name": "Community", "description": "Qualitative community observation reports."},
        {"name": "Nodes", "description": "Node directory and announcement."},
        {"name": "Operations", "description": "Health, metrics, and dashboard pages."},
    ]

    security_schemes = {
        "DeviceToken": {
            "type": "http",
            "scheme": "bearer",
            "description": (
                "Device token issued by POST /bxp/v2/devices/register. "
                "Required for mutations and for ownership checks on DELETE."
            ),
        },
        "NodeToken": {
            "type": "http",
            "scheme": "bearer",
            "description": (
                "Shared secret for inter-node /sync. A deliberate placeholder for "
                "the node trust model that SPEC.md 7 Stage 7 defers to a future RFC."
            ),
        },
    }

    spec["tags"] = tags
    spec["components"] = spec.get("components", {})
    spec["components"]["securitySchemes"] = {
        **spec["components"].get("securitySchemes", {}),
        **security_schemes,
    }

    spec["servers"] = [
        {"url": "http://localhost:5000", "description": "Local reference node"},
    ]

    # Machine-readable provenance for anything that indexes this file.
    spec["x-bxp"] = {
        "protocol": "Breathe Exposure Protocol",
        "specification": "https://github.com/bxpprotocol/bxp-spec/blob/main/SPEC.md",
        "specificationDoi": "https://doi.org/10.5281/zenodo.18906812",
        "implementationDoi": "https://doi.org/10.5281/zenodo.18907003",
        "repository": "https://github.com/bxpprotocol/bxp-spec",
        "license": "Apache-2.0",
        "hriStatus": "experimental",
        "hriWarning": (
            "bxpHri is an experimental composite index. Not clinically or "
            "epidemiologically validated. Do not use for medical decisions."
        ),
        "conformance": {
            "vectors": 17,
            "verify": [
                "python conformance/verify_python.py",
                "node conformance/verify_typescript.mjs",
            ],
        },
    }

    return spec


def to_yaml(spec: dict) -> str:
    try:
        import yaml  # type: ignore
    except ImportError:
        return ""
    return yaml.safe_dump(spec, sort_keys=False, allow_unicode=True, width=100)


def main() -> int:
    spec = build()

    j = REPO / "openapi.json"
    j.write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    y = REPO / "openapi.yaml"
    text = to_yaml(spec)
    if text:
        y.write_text(text, encoding="utf-8")
        print(f"wrote {y.relative_to(REPO)} ({len(text)} bytes)")
    else:
        # PyYAML is not a runtime dependency of the node; the JSON artifact is
        # canonical and the YAML is a convenience for human review.
        print("PyYAML not installed - wrote openapi.json only", file=sys.stderr)

    print(f"wrote {j.relative_to(REPO)}")
    print(f"openapi={spec['openapi']} paths={len(spec.get('paths', {}))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
