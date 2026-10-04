"""Audit the published site for the defects that quietly destroy credibility.

Checks every local href/src actually resolves to a file, flags pages missing
canonical/description/OG metadata, validates JSON-LD parses, and confirms the
sitemap only lists pages that exist.
"""

import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

SITE = Path(r"C:\Users\Aeron\bxpprotocol.github.io")
problems = []


def rel(url: str) -> str | None:
    """Local path a href points at, or None if external/anchor/mailto."""
    u = urlparse(url)
    if u.scheme or u.netloc:
        return None
    if not u.path:
        return None
    # "/" is the site root, which is served by index.html.
    if u.path == "/":
        return "index.html"
    return u.path.lstrip("/")


print(f"auditing {SITE}\n")

pages = sorted(p for p in SITE.glob("*.html"))
print(f"{len(pages)} HTML pages\n")

# ── 1. link integrity ─────────────────────────────────────────────────────
all_files = {p.name for p in SITE.iterdir() if p.is_file()}
checked = 0

for page in pages:
    text = page.read_text(encoding="utf-8", errors="replace")
    for attr in ("href", "src"):
        for m in re.finditer(rf'{attr}="([^"]+)"', text):
            target = m.group(1)
            path = rel(target)
            if path is None:
                continue
            checked += 1
            if path not in all_files:
                problems.append(f"{page.name}: dead local link {attr}=\"{target}\"")

print(f"local links checked: {checked}")

# ── 2. required metadata ──────────────────────────────────────────────────
NEEDED = [
    ("canonical", r'<link[^>]+rel="canonical"'),
    ("description", r'<meta[^>]+name="description"'),
    ("og:title", r'<meta[^>]+property="og:title"'),
    ("og:url", r'<meta[^>]+property="og:url"'),
    ("title", r"<title>[^<]+</title>"),
    ("viewport", r'name="viewport"'),
]

for page in pages:
    text = page.read_text(encoding="utf-8", errors="replace")
    missing = [name for name, pat in NEEDED if not re.search(pat, text)]
    if missing:
        problems.append(f"{page.name}: missing {', '.join(missing)}")

# ── 3. JSON-LD parses ─────────────────────────────────────────────────────
total_ld = 0
for page in pages:
    text = page.read_text(encoding="utf-8", errors="replace")
    for i, block in enumerate(re.findall(
        r'<script type="application/ld\+json">(.*?)</script>', text, re.S
    )):
        total_ld += 1
        try:
            json.loads(block)
        except json.JSONDecodeError as e:
            snippet = block.strip()[:70].replace("\n", " ")
            problems.append(f"{page.name}: JSON-LD block {i} invalid — {e.msg} near {snippet!r}")

print(f"JSON-LD blocks validated: {total_ld}")

# ── 4. sitemap entries exist ──────────────────────────────────────────────
sm = SITE / "sitemap.xml"
if sm.exists():
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    root = ET.parse(sm).getroot()
    urls = [u.find("s:loc", ns).text for u in root.findall("s:url", ns)]
    for u in urls:
        path = rel(u)
        if path and path not in all_files:
            problems.append(f"sitemap.xml lists missing page: {u}")
    print(f"sitemap entries: {len(urls)}")

# ── 5. pages present but orphaned from the nav ────────────────────────────
nav_sources = ["index.html"] + [p.name for p in pages]
linked_from_index = set()
idx = (SITE / "index.html").read_text(encoding="utf-8", errors="replace")
for m in re.finditer(r'href="([^"#]+)"', idx):
    t = rel(m.group(1))
    if t:
        linked_from_index.add(t)

for page in pages:
    if page.name == "index.html":
        continue
    if page.name not in linked_from_index:
        problems.append(f"{page.name}: not linked from index.html (orphaned)")

# ── report ────────────────────────────────────────────────────────────────
print()
if problems:
    print(f"FAIL  {len(problems)} problem(s):\n")
    for p in problems:
        print("  -", p)
    sys.exit(1)

print("OK  no problems found")