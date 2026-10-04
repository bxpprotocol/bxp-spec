#!/usr/bin/env python3
"""Regenerate the SPEC.md table of contents from the actual headings.

The TOC had drifted: five anchors pointed at headings that no longer exist
(wording changed when sections were renamed), and five sections were missing
from it entirely. In a 1600-line normative document that is the difference
between a usable spec and a frustrating one.

Anchor IDs follow GitHub's algorithm closely enough to match it:
lowercase, strip punctuation, spaces to hyphens.

    python scripts/build_spec_toc.py           # rewrite SPEC.md in place
    python scripts/build_spec_toc.py --check   # exit 1 if stale
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SPEC = REPO / "SPEC.md"

START = "## Table of Contents"
END = "\n## 1. Abstract"


def github_slug(text: str) -> str:
    """Approximate GitHub's heading-anchor algorithm."""
    s = text.strip().lower()
    s = re.sub(r"[^\w\- ]+", "", s, flags=re.UNICODE)   # drop punctuation
    s = s.replace(" ", "-")
    return s


def build(text: str) -> str | None:
    lines = text.split("\n")

    headings: list[tuple[str, str]] = []
    for line in lines:
        if line.startswith("## ") and not line.startswith("### "):
            h = line[3:].strip()
            if h == "Table of Contents":
                continue
            headings.append((h, github_slug(h)))

    if not headings:
        return None

    out = [START, ""]
    for i, (h, slug) in enumerate(headings, 1):
        # Sections are cited by number throughout the docs ("SPEC.md §7"), so
        # keep the number. Appendices are cited by letter, so keep the letter.
        if m := re.match(r"^Appendix ([A-D])\s*[—-]\s*(.+)$", h):
            label = f"Appendix {m.group(1)} — {m.group(2)}"
        elif m := re.match(r"^(\d+(?:\.\d+)?)\.?\s+(.+)$", h):
            label = f"{m.group(1)}. {m.group(2)}"
        else:
            label = h
        out.append(f"{i}. [{label}](#{slug})")
    out.append("")

    toc = "\n".join(out)

    start = text.find(START)
    end = text.find(END)
    if start == -1 or end == -1 or end < start:
        return None

    return text[:start] + toc + text[end:]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    original = SPEC.read_text(encoding="utf-8")
    updated = build(original)

    if updated is None:
        print("FAIL  could not locate TOC boundaries in SPEC.md")
        return 1

    if updated == original:
        print("SPEC.md TOC is up to date")
        return 0

    if args.check:
        print("FAIL  SPEC.md table of contents is stale - run scripts/build_spec_toc.py")
        return 1

    SPEC.write_text(updated, encoding="utf-8", newline="\n")
    print(f"SPEC.md TOC regenerated ({updated.count(chr(10) + '. [')} entries)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())