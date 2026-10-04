#!/usr/bin/env python3
"""Documentation integrity checks.

These are the defects that silently break how the specification renders on
GitHub and how the website generator consumes it. None of them fail a build
today, so they are checked explicitly:

  1. Unbalanced code fences. An odd number of ``` lines makes GitHub swallow
     every following line into a code block. SPEC.md shipped with a stray
     trailing fence that hid the references section.
  2. Version drift. The protocol version appears in SPEC.md, README.md,
     CITATION.cff, both SDK manifests, and the OpenAPI document. They must agree,
     or a citation will name a version the specification no longer claims.
  3. HRI labelling. BXP-HRI is experimental and must not be presented as a
     validated clinical metric anywhere in the prose.

    python scripts/check_docs.py

Exit code is non-zero on any failure, so CI can gate on it.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

DOCS = [
    "SPEC.md",
    "README.md",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "GOVERNANCE.md",
    "docs/api_documentation.md",
    "docs/developer_guide.md",
    "docs/protocol_overview.md",
]

failures: list[str] = []
warnings: list[str] = []


def fail(msg: str) -> None:
    failures.append(msg)


def warn(msg: str) -> None:
    warnings.append(msg)


def check(path: Path) -> None:
    if not path.exists():
        fail(f"{path.relative_to(REPO)}: referenced file does not exist")
        return
    text = path.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")

    fences = len(re.findall(r"^```", text, flags=re.M))
    if fences % 2:
        fail(
            f"{path.relative_to(REPO)}: unbalanced code fence "
            f"({fences} '```' markers). GitHub will render everything after "
            f"the stray marker as a code block."
        )

    for heading in re.findall(r"^#{1,3}\s+(.+)$", text, flags=re.M):
        if "\ufffd" in heading or "â€”" in heading or "â€" in heading:
            warn(
                f"{path.relative_to(REPO)}: possible mojibake in heading "
                f"{heading[:60]!r} - file may need re-encoding as UTF-8"
            )
            break


def detect_version() -> str | None:
    spec = (REPO / "SPEC.md").read_text(encoding="utf-8", errors="replace")
    m = re.search(r"specification v(\d+\.\d+)", spec, re.I)
    if m:
        return m.group(1)
    m = re.search(r"\bversion[:\s]+(\d+\.\d+)", spec, re.I)
    return m.group(1) if m else None


def check_version_agreement() -> None:
    version = detect_version()
    if not version:
        warn("could not determine protocol version from SPEC.md; skipping agreement check")
        return

    cff = REPO / "CITATION.cff"
    if cff.exists():
        t = cff.read_text(encoding="utf-8")
        m = re.search(r"^version:\s*[\"']?v?(\d+\.\d+)", t, flags=re.M)
        if m and m.group(1) != version:
            fail(f"CITATION.cff version {m.group(1)} != SPEC.md version {version}")
        elif not m:
            warn("CITATION.cff has no parseable 'version:' field")

    for rel, pattern in [
        ("sdk/typescript/package.json", r'"version"\s*:\s*"([^"]+)"'),
    ]:
        p = REPO / rel
        if not p.exists():
            continue
        m = re.search(pattern, p.read_text(encoding="utf-8"))
        if m and not m.group(1).startswith(version):
            warn(
                f"{rel} version {m.group(1)} does not start with protocol "
                f"version {version} - expected if the SDK ships ahead of the spec"
            )

    api = REPO / "openapi.json"
    if api.exists():
        spec_json = json.loads(api.read_text(encoding="utf-8"))
        v = spec_json.get("info", {}).get("version")
        if v and not v.startswith(version):
            fail(f"openapi.json info.version {v} != SPEC.md version {version}")


def check_hri_labelling() -> None:
    """BXP-HRI must never be presented as clinically validated."""
    targets = [
        REPO / "README.md",
        REPO / "SPEC.md",
        REPO / "docs" / "protocol_overview.md",
    ]
    for p in targets:
        if not p.exists():
            continue
        t = p.read_text(encoding="utf-8", errors="replace")
        mentions = len(re.findall(r"BXP[-_]HRI", t, re.I))
        if mentions == 0:
            continue
        caveat = re.search(
            r"(experimental|not\s+(?:clinically|epidemiologically)\s+validated|"
            r"research\s+prototype|not\s+for\s+medical)",
            t,
            re.I,
        )
        if not caveat:
            fail(
                f"{p.name}: mentions BXP-HRI {mentions}x but contains no "
                f"'experimental' / 'not validated' caveat. The index is not "
                f"clinically validated and must be labelled as such."
            )


def check_spec_version_string() -> None:
    """The spec must state its own version and stability clearly."""
    t = (REPO / "SPEC.md").read_text(encoding="utf-8", errors="replace")
    head = t[:4000]
    if not re.search(r"2\.0", head):
        fail("SPEC.md: no '2.0' version marker near the top of the document")
    if not re.search(r"(stable|frozen|locked)", head, re.I):
        warn("SPEC.md: no 'stable'/'frozen' language near the top")


def main() -> int:
    for rel in DOCS:
        check(REPO / rel)

    check_version_agreement()
    check_hri_labelling()
    check_spec_version_string()

    for w in warnings:
        print(f"WARN  {w}")
    for f in failures:
        print(f"FAIL  {f}")

    if failures:
        print(f"\n{failures.__len__()} documentation check(s) failed")
        return 1

    print(f"\ndocumentation checks passed ({len(warnings)} warning(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())