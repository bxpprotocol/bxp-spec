#!/usr/bin/env python3
"""Publish the project's machine-readable and downloadable artefacts to the site.

Two problems this solves.

1. `llms.txt` advertised `llms-full.txt` and that file did not exist. A broken
   promise in the AI-retrieval surface is worse than no promise, so it is
   generated here from the actual documents rather than hand-maintained.

2. The OpenAPI contract was only reachable cross-origin from
   raw.githubusercontent.com. API directories, code generators, and developer
   search look for a contract on the product's own domain. It is copied here so
   `https://bxpprotocol.github.io/openapi.json` resolves.

Everything written is derived from a file already in the repository, so the
site cannot drift from the source of truth.

    python scripts/build_site_artifacts.py --out ../bxpprotocol.github.io
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SITE = "https://bxpprotocol.github.io"


def strip_md(md: str) -> str:
    """Flatten Markdown to readable plain text for llms-full.txt."""
    out = []
    in_fence = False
    for line in md.split("\n"):
        if line.startswith("```"):
            in_fence = not in_fence
            out.append("")
            continue
        if in_fence:
            out.append(line)
            continue
        line = re.sub(r"^#{1,6}\s+", "", line)
        line = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", line)
        line = re.sub(r"^\s*[-*]\s+", "- ", line)
        line = re.sub(r"^\|", "| ", line)
        line = re.sub(r"[*`]", "", line)
        out.append(line)
    text = "\n".join(out)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def build_llms_full() -> str:
    """The extended retrieval corpus: the documents an assistant actually needs."""
    parts: list[str] = [
        "# BXP — Breathe Exposure Protocol",
        "",
        "Extended documentation for retrieval. This file contains the substantive",
        "content of the BXP specification, API documentation, and developer guide",
        "in plain text, so an assistant can answer questions about the format, the",
        "API, and the conformance model without fetching five separate documents.",
        "",
        "For navigation rather than content, see https://bxpprotocol.github.io/llms.txt",
        "",
        "**BXP-HRI is experimental and is not clinically validated.** It must not be",
        "used for medical decisions.",
        "",
        "---",
        "",
    ]

    docs = [
        ("SPECIFICATION v2.0", "SPEC.md"),
        ("API DOCUMENTATION", "docs/api_documentation.md"),
        ("DEVELOPER GUIDE", "docs/developer_guide.md"),
        ("PROTOCOL OVERVIEW", "docs/protocol_overview.md"),
    ]

    for label, rel in docs:
        p = REPO / rel
        if not p.exists():
            continue
        parts.append("")
        parts.append("=" * 78)
        parts.append(f"## {label}")
        parts.append(f"Source: https://github.com/bxpprotocol/bxp-spec/blob/main/{rel}")
        parts.append("=" * 78)
        parts.append("")
        parts.append(strip_md(p.read_text(encoding="utf-8", errors="replace")))
        parts.append("")

    return "\n".join(parts).rstrip() + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(REPO))
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    # 1. llms-full.txt — the corpus llms.txt already promised.
    full = build_llms_full()
    (out / "llms-full.txt").write_text(full, encoding="utf-8")
    print(f"wrote llms-full.txt ({len(full):,} bytes)")

    # 2. The API contract on the product's own domain.
    copied = []
    for name in ("openapi.json", "openapi.yaml"):
        src = REPO / name
        if src.exists():
            shutil.copyfile(src, out / name)
            copied.append(name)

    spec = json.loads((REPO / "openapi.json").read_text(encoding="utf-8"))
    paths = len(spec.get("paths", {}))
    ops = sum(len(v) for v in spec.get("paths", {}).values())
    if copied:
        print(f"copied {', '.join(copied)} ({paths} paths, {ops} operations)")

    # 3. The sample dataset, so it is downloadable rather than repo-only.
    ds = REPO / "datasets" / "sample_readings.bxp.json"
    if ds.exists():
        shutil.copyfile(ds, out / "sample_readings.bxp.json")
        doc = json.loads(ds.read_text(encoding="utf-8"))
        print(f"copied sample_readings.bxp.json ({doc.get('recordCount', '?')} readings)")

    # 4. The Postman collection, so integrators need not clone the repo first.
    pm = REPO / "postman" / "BXP_Protocol.postman_collection.json"
    if pm.exists():
        shutil.copyfile(pm, out / "BXP_Protocol.postman_collection.json")
        print("copied BXP_Protocol.postman_collection.json")

    # 5. .nojekyll — GitHub Pages runs Jekyll on branch deploys, which can drop
    #    files it considers underscore-prefixed or otherwise unwanted. The site
    #    is plain static files and must be served verbatim.
    (out / ".nojekyll").write_text("", encoding="utf-8")
    print("wrote .nojekyll")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())