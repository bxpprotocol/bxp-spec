#!/usr/bin/env python3
"""Generate an Atom feed of BXP releases from CHANGELOG.md.

A published feed gives release watchers, mirrors, and CI consumers a
machine-readable subscription without polling GitHub. Without one, downstream
projects have to scrape HTML to notice a new version.

    python scripts/build_feed.py --out ../bxpprotocol.github.io

Content is derived from CHANGELOG.md so the feed and the changelog cannot
disagree about what shipped.
"""

from __future__ import annotations

import argparse
import re
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

REPO = Path(__file__).resolve().parent.parent
SITE = "https://bxpprotocol.github.io"

HEAD = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>BXP Protocol releases</title>
  <subtitle>Open protocol and API for atmospheric exposure data interoperability.</subtitle>
  <id>{site}/feed.xml</id>
  <link rel="self" href="{site}/feed.xml"/>
  <link rel="alternate" href="{site}/"/>
  <updated>{updated}</updated>
  <author><name>BXP Protocol contributors</name></author>
  <rights>Apache-2.0</rights>
"""


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def parse_releases(changelog: str) -> list[dict]:
    """Split the changelog into releases.

    Recognises both `## [2.1.0] - 2026-10-02` and `## 2.1.0 — 2026-10-02`
    so it works with either heading style.
    """
    parts = re.split(r"^##\s+", changelog, flags=re.M)[1:]
    releases = []
    for part in parts:
        first = part.split("\n", 1)[0].strip()
        m = re.match(r"\[?([\d]+\.[\d]+(?:\.[\d]+)?)\]?\s*[—–-]?\s*(\S*.*)?$", first)
        if not m:
            continue
        version = m.group(1)
        rest = (m.group(2) or "").strip()
        rest = re.sub(r"^[—–-]\s*", "", rest).strip()

        date = None
        dm = re.search(r"(\d{4}-\d{2}-\d{2})", rest)
        if dm:
            date = dm.group(1)
            label = rest.split("—")[0].split("(")[0].strip()
        else:
            # A month-only heading ("March 2026") cannot be rendered as a
            # timestamp without inventing a day. Keep the text, leave date None,
            # and let the entry fall back to the changelog rather than a lie.
            label = rest or f"Version {version}"

        # Release body: everything until the next `## ` heading.
        body = part.split("\n", 1)[1] if "\n" in part else ""
        body = re.sub(r"\[([^\]]+)\]\[([^\]]*)\]", r"\1", body)  # flatten link refs
        body = body.strip()

        summary = ""
        for line in body.split("\n"):
            line = line.strip()
            if line and not line.startswith(("#", "-", "*", ">")):
                summary = line
                break
        if not summary:
            bullets = re.findall(r"^[-*]\s+(.+)$", body, flags=re.M)
            summary = bullets[0] if bullets else label

        releases.append(
            {
                "version": version,
                "label": label,
                "date": date,
                "body": body,
                "summary": summary,
            }
        )
    return releases


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(REPO))
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    changelog = (REPO / "CHANGELOG.md").read_text(encoding="utf-8")
    releases = parse_releases(changelog)

    if not releases:
        print("warning: no releases parsed from CHANGELOG.md", flush=True)

    newest_date = next(
        (r["date"] for r in releases if r["date"]),
        None,
    )
    if newest_date is None:
        print("warning: no full release dates found in CHANGELOG.md", flush=True)
        newest_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    updated = f"{newest_date}T00:00:00Z"

    parts = [HEAD.format(site=SITE, updated=updated)]

    undated = 0
    for r in releases[:20]:
        # An entry without a real date is published with the feed's own
        # timestamp. That is weaker than omitting it, so it is flagged.
        if r["date"]:
            stamp = f"{r['date']}T00:00:00Z"
        else:
            stamp = updated
            undated += 1
        tag = f"v{r['version']}"
        url = f"https://github.com/bxpprotocol/bxp-spec/releases/tag/{tag}"
        # Flatten the body to plain text: an Atom <content> would otherwise
        # need embedded HTML and risk malformed XML.
        text = re.sub(r"^#{1,6}\s+", "", r["body"], flags=re.M)
        text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
        text = re.sub(r"[*`>]", "", text)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()[:4000]

        parts.append(
            f"""  <entry>
    <title>v{r['version']} — {escape(r['label'])}</title>
    <id>{url}</id>
    <link rel="alternate" href="{url}"/>
    <updated>{stamp}</updated>
    <summary>{escape(r['summary'])}</summary>
    <content type="text">{escape(text)}</content>
  </entry>
"""
        )

    parts.append("</feed>\n")

    path = out / "feed.xml"
    path.write_text("".join(parts), encoding="utf-8")
    print(f"wrote {path.name} ({len(releases)} release(s), {len(''.join(parts)):,} bytes)")
    if undated:
        print(f"warning: {undated} release(s) lack a full YYYY-MM-DD date in CHANGELOG.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())