"""Verify every in-page anchor link in a Markdown file resolves to a real heading.

GitHub resolves ``[text](#anchor)`` against a heading slug derived as:
lowercase, drop punctuation, spaces -> hyphens. A stale TOC in a normative
document is invisible until someone clicks it, so this is checked in CI.
"""

import re
import sys
from pathlib import Path


def slug(text: str) -> str:
    s = text.strip().lower()
    s = re.sub(r"[^\w\- ]+", "", s, flags=re.UNICODE)
    return s.replace(" ", "-")


def check(path: str) -> int:
    p = Path(path)
    text = p.read_text(encoding="utf-8").replace("\r\n", "\n")
    lines = text.split("\n")

    in_fence = False
    anchors: dict[str, str] = {}
    for line in lines:
        if line.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = re.match(r"^#{1,6}\s+(.*)$", line)
        if m:
            s = slug(m.group(1))
            # GitHub de-duplicates repeated headings with a numeric suffix.
            n = anchors.get(s, 0)
            anchors[s] = n + 1
            if n:
                s = f"{s}-{n}"

    broken = []
    in_fence = False
    for i, line in enumerate(lines, 1):
        if line.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        for m in re.finditer(r"\[([^\]]*)\]\(#([^)]+)\)", line):
            if m.group(2) not in anchors:
                broken.append((i, m.group(2), m.group(1)))

    if broken:
        print(f"FAIL  {path}: {len(broken)} broken in-page anchor(s)")
        for ln, a, txt in broken[:20]:
            print(f"        line {ln}: #{a}  (link text: {txt!r})")
        return 1

    print(f"OK    {path}: {len(anchors)} headings, all in-page anchors resolve")
    return 0


if __name__ == "__main__":
    rc = 0
    for target in sys.argv[1:]:
        rc |= check(target)
    raise SystemExit(rc)