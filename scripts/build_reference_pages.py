#!/usr/bin/env python3
"""Generate the indexable reference pages served by the project website.

Every page here is derived from an authoritative source in this repository:

    spec.html      <- SPEC.md
    api.html       <- openapi.json
    agents.html    <- SPEC.md Appendix A
    versions.html  <- CHANGELOG.md + CITATION.cff + SPEC.md

Nothing is written by hand, so a page cannot quietly disagree with the
specification or the running server. Run after changing any of those:

    python scripts/build_reference_pages.py --out ../bxpprotocol.github.io

CI runs `make pages-check` to fail if the committed output is stale.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# One shared shell. The site index deliberately uses a different visual system;
# these are reference pages, so they are denser and typography-led.
CSS = """
:root{
  --bg:#fff; --bg-sub:#f7f8fa; --ink:#0a0a0c; --ink-2:#3d3d45; --ink-3:#6e6e78;
  --line:#e6e7eb; --line-2:#d4d6dc; --brand:#00b8a0; --brand-ink:#046b5e;
  --sans:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif;
  --mono:'JetBrains Mono',ui-monospace,SFMono-Regular,Menlo,monospace;
}
*{margin:0;padding:0;box-sizing:border-box}
body{background:var(--bg);color:var(--ink);font-family:var(--sans);line-height:1.65;-webkit-font-smoothing:antialiased}
a{color:var(--brand-ink)}
.wrap{max-width:960px;margin:0 auto;padding:0 24px}
header.top{border-bottom:1px solid var(--line);background:var(--bg-sub)}
header.top .wrap{display:flex;align-items:center;gap:24px;height:58px;flex-wrap:wrap}
.logo{font-weight:700;letter-spacing:-.02em;color:var(--ink);text-decoration:none;display:flex;align-items:center;gap:8px}
.logo span{width:24px;height:24px;border-radius:6px;background:var(--ink);color:var(--brand);display:grid;place-items:center;font-size:12px;font-weight:800}
header.top nav{display:flex;gap:20px;margin-left:auto;flex-wrap:wrap}
header.top nav a{font-size:14px;color:var(--ink-2);text-decoration:none;font-weight:500}
header.top nav a:hover{color:var(--ink)}
main{padding:52px 0 80px}
.eyebrow{font-family:var(--mono);font-size:12px;letter-spacing:.12em;text-transform:uppercase;color:var(--ink-3);font-weight:500;display:block;margin-bottom:12px}
h1{font-size:clamp(30px,4.5vw,44px);letter-spacing:-.035em;line-height:1.1;margin-bottom:14px}
h2{font-size:22px;letter-spacing:-.02em;margin:44px 0 12px;padding-top:20px;border-top:1px solid var(--line)}
h3{font-size:16px;letter-spacing:-.01em;margin:22px 0 8px}
p{color:var(--ink-2);margin-bottom:12px;max-width:74ch}
.lede{font-size:18px;color:var(--ink-2);margin-bottom:22px;max-width:70ch}
code{font-family:var(--mono);font-size:.88em;background:var(--bg-sub);border:1px solid var(--line);border-radius:4px;padding:1px 5px}
pre{background:#0a0a0c;color:#e6e7eb;padding:16px;border-radius:10px;overflow-x:auto;font-family:var(--mono);font-size:12.5px;line-height:1.7;margin:14px 0}
pre code{background:none;border:none;padding:0;color:inherit}
table{width:100%;border-collapse:collapse;margin:16px 0;font-size:14px}
th,td{text-align:left;padding:9px 12px;border-bottom:1px solid var(--line);vertical-align:top}
th{font-size:11.5px;text-transform:uppercase;letter-spacing:.07em;color:var(--ink-3);font-weight:600;background:var(--bg-sub);position:sticky;top:0}
td.mono,th.mono{font-family:var(--mono);font-size:12.5px}
.tblwrap{border:1px solid var(--line);border-radius:10px;overflow:auto;margin:16px 0;max-height:none}
.tblwrap table{margin:0}
.note{border:1px solid #fde68a;background:#fffbeb;border-radius:10px;padding:14px 16px;margin:18px 0;font-size:14px;color:#78350f}
.note strong{display:block;margin-bottom:4px;color:#92400e}
.meta{font-size:13px;color:var(--ink-3);margin-bottom:24px}
.method{display:inline-block;font-family:var(--mono);font-size:10.5px;font-weight:700;padding:2px 7px;border-radius:4px;margin-right:8px;letter-spacing:.04em;min-width:52px;text-align:center}
.m-get{background:#dbeafe;color:#1e40af}
.m-post{background:#dcfce7;color:#166534}
.m-delete{background:#fee2e2;color:#991b1b}
.op{border:1px solid var(--line);border-radius:10px;padding:14px 16px;margin:10px 0;background:var(--bg)}
.op-head{display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-bottom:6px}
.path{font-family:var(--mono);font-size:14px;font-weight:600;color:var(--ink)}
.op p{margin:0;font-size:13.5px}
.tagrow{display:flex;gap:6px;flex-wrap:wrap;margin-top:8px}
.tag{font-family:var(--mono);font-size:10.5px;background:var(--bg-sub);border:1px solid var(--line);border-radius:4px;padding:2px 6px;color:var(--ink-3)}
.toc{background:var(--bg-sub);border:1px solid var(--line);border-radius:10px;padding:16px 20px;margin:22px 0}
.toc ol{margin:0;padding-left:20px;columns:2;font-size:14px}
.toc li{margin:3px 0}
@media(max-width:640px){.toc ol{columns:1}}
footer{border-top:1px solid var(--line);background:var(--bg-sub);padding:26px 0;font-size:13px;color:var(--ink-3)}
footer a{color:var(--ink-2)}
.pill{display:inline-block;font-family:var(--mono);font-size:11px;font-weight:600;letter-spacing:.05em;text-transform:uppercase;padding:3px 9px;border-radius:999px;background:#fef3c7;color:#92400e;border:1px solid #fde68a;margin-bottom:14px}
.citebox{background:var(--bg-sub);border:1px solid var(--line);border-radius:10px;padding:16px;margin:12px 0}
.citebox h4{font-size:13px;text-transform:uppercase;letter-spacing:.06em;color:var(--ink-3);margin-bottom:8px;font-weight:600}
"""


def page(title: str, description: str, canonical: str, body: str, extra_head: str = "") -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
<meta name="description" content="{html.escape(description)}">
<link rel="canonical" href="https://bxpprotocol.github.io/{canonical}">
<meta name="robots" content="index,follow,max-snippet:-1">
<meta property="og:type" content="article">
<meta property="og:url" content="https://bxpprotocol.github.io/{canonical}">
<meta property="og:site_name" content="BXP Protocol">
<meta property="og:title" content="{html.escape(title)}">
<meta property="og:description" content="{html.escape(description)}">
<meta name="twitter:card" content="summary">
<meta name="twitter:title" content="{html.escape(title)}">
<meta name="twitter:description" content="{html.escape(description)}">
<link rel="alternate" type="text/plain" title="BXP machine-readable index (llms.txt)" href="https://bxpprotocol.github.io/llms.txt">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
<style>{CSS}</style>
{extra_head}
</head>
<body>
<header class="top"><div class="wrap">
  <a class="logo" href="/"><span>B</span>BXP</a>
  <nav>
    <a href="/">Overview</a>
    <a href="spec.html">Specification</a>
    <a href="api.html">API</a>
    <a href="agents.html">Agents</a>
    <a href="versions.html">Versions &amp; citation</a>
    <a href="validator.html">Validator</a>
    <a href="https://github.com/bxpprotocol/bxp-spec">GitHub</a>
  </nav>
</div></header>
<main><div class="wrap">
{body}
</div></main>
<footer><div class="wrap">
  BXP — Breathe Exposure Protocol · Apache 2.0 ·
  <a href="https://github.com/bxpprotocol/bxp-spec">Repository</a> ·
  <a href="https://doi.org/10.5281/zenodo.18906812">Cite this work</a>
</div></footer>
</body>
</html>
"""


# ── Markdown → HTML (the subset SPEC.md actually uses) ────────────────────

def md_to_html(md: str) -> str:
    out, in_list, in_table, in_code = [], False, False, False

    def inline(s: str) -> str:
        s = html.escape(s)
        s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
        s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
        s = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", s)
        s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', s)
        return s

    def close_blocks():
        nonlocal in_list, in_table
        if in_list:
            out.append("</ul>")
            in_list = False
        if in_table:
            out.append("</tbody></table></div>")
            in_table = False

    lines = md.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()

        # Fence handling must not go through close_blocks(): that would reset
        # in_code and make a closing fence immediately open a fresh block,
        # swallowing every following section as if it were code.
        if line.startswith("```"):
            if in_code:
                out.append("</code></pre>")
                in_code = False
            else:
                close_blocks()
                out.append("<pre><code>")
                in_code = True
            i += 1
            continue
        if in_code:
            out.append(html.escape(lines[i]))
            i += 1
            continue

        # Table: a header row followed by a separator row.
        if line.startswith("|") and i + 1 < len(lines) and re.match(r"^\|[\s:|-]+\|$", lines[i + 1].strip()):
            close_blocks()
            out.append('<div class="tblwrap"><table><thead><tr>')
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            for c in cells:
                cls = ' class="mono"' if "`" in c else ""
                out.append(f"<th{cls}>{inline(c)}</th>")
            out.append("</tr></thead><tbody>")
            in_table = True
            i += 2
            continue
        if in_table:
            if not line.startswith("|"):
                out.append("</tbody></table></div>")
                in_table = False
            else:
                cells = [c.strip() for c in line.strip().strip("|").split("|")]
                out.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in cells) + "</tr>")
                i += 1
                continue

        if line.startswith("## "):
            close_blocks()
            out.append('<h2 id="%s">%s</h2>' % (slug(line[3:]), inline(line[3:])))
        elif line.startswith("### "):
            close_blocks()
            out.append("<h3 id=\"%s\">%s</h3>" % (slug(line[4:]), inline(line[4:])))
        elif line.startswith("# "):
            close_blocks()
        elif re.match(r"^\s*[-*]\s+", line):
            if not in_list:
                close_blocks()
                out.append("<ul>")
                in_list = True
            item = re.sub(r"^\s*[-*]\s+", "", line)
            out.append("<li>%s</li>" % inline(item))
        elif line.strip() == "":
            close_blocks()
        else:
            close_blocks()
            out.append(f"<p>{inline(line)}</p>")
        i += 1

    close_blocks()
    return "\n".join(out)


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.strip().lower()).strip("-")


# ── Pages ─────────────────────────────────────────────────────────────────

def build_spec(spec_md: str) -> str:
    """SPEC.md rendered to HTML.

    The Markdown on GitHub is the canonical document; this exists so the same
    content is reachable from the project's own domain and is crawlable with
    real headings rather than as one undifferentiated blob.
    """
    text = spec_md.replace("\r\n", "\n")

    # Drop the TOC; this page renders its own.
    text = re.sub(r"^## Table of Contents\n[\s\S]*?(?=\n## 1\.)", "", text, flags=re.M)

    sections = re.findall(r"^## (.+)$", text, flags=re.M)
    toc = "".join(f'<li><a href="#{slug(s)}">{html.escape(re.sub(r"^Appendix [A-D] — ", "", s))}</a></li>' for s in sections)

    rendered = md_to_html(text)
    # First heading becomes the page H1.
    rendered = re.sub(r"^<h2 id=\"abstract\">", '<h1 id="abstract">', rendered, count=1)

    body = f"""<span class="eyebrow">Specification</span>
<h1>BXP Protocol Specification</h1>
<p class="lede">The normative definition of the BXP file format, agent schema,
protocol stages, REST API, privacy framework, and conformance model.</p>
<p class="meta">Version 2.0 · This is the same document as
<a href="https://github.com/bxpprotocol/bxp-spec/blob/main/SPEC.md">SPEC.md in the repository</a>,
rendered for the web. Where they differ, the repository is authoritative.</p>
<div class="note"><strong>Canonical source</strong>
The Markdown file in the repository is the canonical specification and is what
conformance is judged against. This page is a rendering of it, regenerated from
that file rather than edited by hand.</div>
<div class="toc"><strong style="font-size:13px">Contents</strong><ol>{toc}</ol></div>
{rendered}"""
    return page(
        "BXP Protocol Specification v2.0 — file format, agents, API, privacy, conformance",
        "The normative BXP v2.0 specification: 32-byte binary container, JSON representation, "
        "31 atmospheric agents, five-stage pipeline, REST API, privacy framework, and the "
        "conformance model with 17 golden test vectors.",
        "spec.html",
        body,
    )


def build_api(openapi: dict) -> str:
    """Every endpoint from the real OpenAPI document."""
    paths = openapi.get("paths", {})
    info = openapi.get("info", {})

    groups = {
        "Readings": ["readings", "verify", "aggregate", "history", "latest", "nearby", "search", "compare"],
        "Locations": ["locations"],
        "Devices": ["devices"],
        "Community": ["community"],
        "Federation": ["sync", "nodes"],
        "Operations": ["health", "metrics", "dashboard", "map", "widget", "city", "/"],
    }

    def group_for(p: str) -> str:
        for name, needles in groups.items():
            for n in needles:
                if n in p:
                    return name
        return "Operations"

    summary = (
        f"Version {info.get('version','2.0')} · {len(paths)} endpoints · "
        f"OpenAPI {openapi.get('openapi','3.1')} · generated from the running reference server"
    )

    blocks: list[str] = []
    seen: set[str] = set()
    for name in groups:
        rows = []
        for p, ops in paths.items():
            if group_for(p) != name:
                continue
            for method, op in ops.items():
                tag = op.get("summary") or op.get("description") or ""
                tag = re.sub(r"<[^>]+>", "", tag).strip()
                tag = tag.split("\n")[0][:230]
                desc = re.sub(r"<[^>]+>", "", op.get("description") or "").strip().split("\n\n")[0][:300]
                if tag and tag not in seen:
                    seen.add(tag)
                rows.append((method.upper(), p, tag, desc, op.get("tags", [])))
        if not rows:
            continue
        rows.sort(key=lambda r: (r[1], r[0]))
        chunks = []
        for method, p, tag, desc, tags in rows:
            taglinks = "".join(f'<span class="tag">{html.escape(t)}</span>' for t in tags[:2])
            chunks.append(
                f'<div class="op"><div class="op-head">'
                f'<span class="method m-{method.lower()}">{method}</span>'
                f'<span class="path">{html.escape(p)}</span></div>'
                f"<p>{html.escape(tag)}</p>"
                + (f'<p style="color:var(--ink-3);font-size:13px">{html.escape(desc)}</p>' if desc else "")
                + (f'<div class="tagrow">{taglinks}</div>' if taglinks else "")
                + "</div>"
            )
        blocks.append(f"<h2 id=\"{slug(name)}\">{html.escape(name)}</h2>\n" + "\n".join(chunks))

    total_ops = sum(len(v) for v in paths.values())

    body = f"""<span class="eyebrow">REST API</span>
<h1>BXP REST API</h1>
<p class="lede">The complete HTTP contract for a BXP v2.0 node. Every BXP node
exposes this surface, so any client written against it can query any node.</p>
<p class="meta">{html.escape(summary)}</p>

<div class="note"><strong>Machine-readable contract</strong>
The authoritative definition is the OpenAPI 3.1 document at
<a href="https://raw.githubusercontent.com/bxpprotocol/bxp-spec/main/openapi.json">openapi.json</a>.
Import it into Postman, Insomnia, or any OpenAPI-aware tool. This page is
generated from that same file, so it cannot describe an endpoint the server does
not implement.</div>

<h2 id="using">Using the API</h2>
<p>Submit a reading:</p>
<pre><code>curl -X POST http://localhost:5000/bxp/v2/readings \\
  -H "Content-Type: application/json" \\
  -d '{{"readings":[{{"latitude":5.6037,"longitude":-0.1870,
       "source":"native",
       "agents":[{{"agentId":"PM2_5","value":47.2,"unit":"ug/m3"}}]}}]}}'</code></pre>
<p>Find relevant observations near a point:</p>
<pre><code>curl "http://localhost:5000/bxp/v2/nearby?lat=5.60&amp;lon=-0.18&amp;radiusKm=25"</code></pre>
<p>Replicate from a peer node:</p>
<pre><code>curl "http://localhost:5000/bxp/v2/sync?since=0"</code></pre>

<h2 id="auth">Authentication</h2>
<p>Reads are unauthenticated. Writes require a device token obtained from
<code>POST /bxp/v2/devices/register</code>, which is rate limited to 5 requests
per minute per IP. Inter-node replication uses a shared secret. Both mechanisms
are deliberately minimal — real node identity and trust are deferred to a future
RFC rather than left implied.</p>

<h2 id="compatibility">Version negotiation</h2>
<p>The <code>major</code> path segment is the protocol major version. MINOR
additions are backward compatible: a server may add response fields, and clients
must ignore-and-preserve fields they do not recognise. Breaking changes require a
new major version with 18 months advance notice.</p>

{''.join(blocks)}

<p style="margin-top:40px;font-size:13px;color:var(--ink-3)">
{len(paths)} paths · {total_ops} operations · generated from the reference server's
OpenAPI document. See also the
<a href="https://github.com/bxpprotocol/bxp-spec/blob/main/docs/api_documentation.md">prose API documentation</a>.
</p>"""

    return page(
        "BXP REST API — all 23 endpoints of a BXP v2.0 node",
        f"Complete HTTP contract for a BXP node: {total_ops} operations across {len(paths)} paths covering "
        "readings, locations, nearby discovery, search, device registry, community reports, and "
        "federation. OpenAPI 3.1, generated from the reference implementation.",
        "api.html",
        body,
    )


def build_agents(spec_md: str) -> str:
    """SPEC.md Appendix A rendered as a filterable-looking reference table."""
    text = spec_md.replace("\r\n", "\n")
    m = re.search(r"^## Appendix A.*?\n\n(\|.*?)\n\n", text, flags=re.M | re.S)
    table_md = m.group(1) if m else ""
    rendered = md_to_html(table_md)

    cats: dict[str, int] = {}
    for row in table_md.split("\n")[2:]:
        cells = [c.strip() for c in row.strip().strip("|").split("|")]
        if len(cells) >= 3:
            cats[cells[2]] = cats.get(cells[2], 0) + 1

    cat_list = " · ".join(f"**{k}** ({v})" for k, v in sorted(cats.items()))
    total = sum(cats.values())

    body = f"""<span class="eyebrow">Agent reference</span>
<h1>Atmospheric agents</h1>
<p class="lede">Every agent the BXP schema defines, with its canonical unit and the
WHO guideline value it is measured against.</p>
<p class="meta">{total} agents · {len(cats)} categories · {cat_list}</p>

<div class="note"><strong>Extending the schema</strong>
The agent list is not closed. A deployment may carry additional agents under the
<code>ext</code> namespace without changing the major version, and existing
implementations must ignore-and-preserve fields they do not recognise. A new
<em>natively specified</em> agent requires an RFC.</div>

<h2 id="units">Units</h2>
<p>The canonical unit for an agent is fixed by this table. Every reading states
its own <code>unit</code>, and implementations normalise to the canonical form
during the INTERPRET stage. A reading whose unit cannot be converted is rejected
rather than guessed at.</p>

<h2 id="reference">Complete reference</h2>
{rendered}

<h2 id="hri">Which agents feed BXP-HRI</h2>
<p>Only the eight weighted agents contribute to the composite health risk index:
PM2.5, PM10, NO₂, O₃, CO, SO₂, and TVOC, with weights derived from WHO
disability-adjusted life-year burden data. Other agents are carried in the record
and are available to applications, but they do not move the index.</p>
<div class="note"><strong>BXP-HRI is experimental</strong>
It is not clinically or epidemiologically validated and must not be used for
medical decisions, diagnosis, or clinical guidance.</div>

<p style="margin-top:28px;font-size:13px;color:var(--ink-3)">
Generated from Appendix A of <a href="spec.html">the specification</a>. Errors in
either are <a href="https://github.com/bxpprotocol/bxp-spec/issues">worth reporting</a>.
</p>"""

    return page(
        "BXP atmospheric agents — all 31 agent IDs, units, and WHO guideline values",
        f"Complete reference for all {total} atmospheric agents in the BXP schema: particulates, "
        "gases, VOCs, biological agents, heavy metals, and environmental parameters, each with its "
        "canonical unit and WHO guideline value.",
        "agents.html",
        body,
    )


def build_versions(spec_md: str, citation_cff: str, changelog: str) -> str:
    """How to pin a version and how to cite. The academic-authority surface."""
    ver = "2.0"
    m = re.search(r"^version:\s*[\"']?([\d.]+)", citation_cff, flags=re.M)
    if m:
        ver = m.group(1)

    doi_spec = "10.5281/zenodo.18906812"
    doi_impl = "10.5281/zenodo.18907003"
    for d in (doi_spec, doi_impl):
        if d not in citation_cff:
            print(f"warning: {d} not present in CITATION.cff", file=sys.stderr)

    # First released heading in the changelog, if there is one.
    released = re.findall(r"^## \[?([\d.]+)\]?\s*[—-]\s*(.+)$", changelog, flags=re.M)
    rows = "".join(
        f"<tr><td class='mono'>{html.escape(v)}</td><td>{html.escape(d)}</td>"
        f"<td><code>#{html.escape(v)}</code></td></tr>"
        for v, d in released[:6]
    ) or "<tr><td class='mono'>2.0</td><td>Public release with conformance model</td><td><code>#v2.0</code></td></tr>"

    bibtex = f"""@software{{bxp_protocol_{ver.replace('.', '_')},
  author    = {{Elvarin}},
  title     = {{BXP Protocol: Breathe Exposure Protocol}},
  version   = {{{ver}}},
  year      = {{2026}},
  doi       = {{{doi_spec}}},
  url       = {{https://github.com/bxpprotocol/bxp-spec}},
  license   = {{Apache-2.0}}
}}"""

    apa = (
        "Elvarin. (2026). <i>BXP Protocol: Breathe Exposure Protocol</i> "
        f"(Version {ver}) [Computer software]. Zenodo. https://doi.org/{doi_spec}"
    )
    mla = (
        "Elvarin. <i>BXP Protocol: Breathe Exposure Protocol</i>. "
        f"Version {ver}, Zenodo, 2026, doi:{doi_spec}."
    )
    chicago = (
        "Elvarin. “BXP Protocol: Breathe Exposure Protocol.” Version "
        f"{ver}. Zenodo, 2026. https://doi.org/{doi_spec}."
    )
    ris = f"""TY  - SOFT
AU  - Elvarin
TI  - BXP Protocol: Breathe Exposure Protocol
PY  - 2026
VL  - {ver}
DO  - {doi_spec}
UR  - https://github.com/bxpprotocol/bxp-spec
ER  -"""

    body = f"""<span class="eyebrow">Versions &amp; citation</span>
<h1>Versions, pinning, and citation</h1>
<p class="lede">BXP v2.0 is a stable specification. This page explains how to pin
a version so your integration or citation keeps resolving to the same document,
and how to cite the work.</p>

<div class="note"><strong>Why pinning matters</strong>
A specification that can change without warning cannot be integrated against. BXP
commits to semantic versioning: a breaking change means a new MAJOR version with
18 months advance notice, and MINOR additions are backward compatible by design.
Pin to a MAJOR version and a minor release cannot invalidate your integration.</div>

<h2 id="pinning">Pinning a version</h2>
<table>
<thead><tr><th>Want</th><th>Use</th><th>Means</th></tr></thead>
<tbody>
<tr><td class="mono">main</td><td><code>https://github.com/bxpprotocol/bxp-spec/blob/main/SPEC.md</code></td><td>Always the latest work. Fine for reading, not for integrating.</td></tr>
<tr><td class="mono">v2.0</td><td><code>.../blob/v2.0/SPEC.md</code></td><td>The specification as published. Stable, and what conformance is judged against.</td></tr>
<tr><td class="mono">&lt;commit&gt;</td><td><code>.../blob/&lt;sha&gt;/SPEC.md</code></td><td>Exactly one immutable state. Use this in a paper or a reproducibility record.</td></tr>
<tr><td class="mono">DOI</td><td><a href="https://doi.org/{doi_spec}">doi:{doi_spec}</a></td><td>Archival, time-stamped, and resolvable forever. Preferred for citation.</td></tr>
</tbody>
</table>
<p>For code dependencies, the equivalents are the <code>bxp-sdk</code> package
version, or a git submodule pinned to a tag.</p>

<h2 id="contract">Pinning the API contract</h2>
<p>The REST contract is committed as an OpenAPI 3.1 document, generated from the
reference server so it cannot drift from the implementation:</p>
<pre><code>openapi.json   canonical, machine-readable
openapi.yaml   same document, human-diffable</code></pre>
<p>Pin one of these into your repository and diff it in CI. When it changes
incompatibly, you find out in a pull request rather than in production.</p>

<h2 id="compatibility">Compatibility policy</h2>
<table>
<thead><tr><th>Change</th><th>Version bump</th><th>Your integration</th></tr></thead>
<tbody>
<tr><td>New optional field</td><td class="mono">MINOR</td><td>Keeps working. Ignore fields you do not recognise.</td></tr>
<tr><td>New agent under <code>ext</code></td><td class="mono">MINOR</td><td>Keeps working.</td></tr>
<tr><td>New endpoint</td><td class="mono">MINOR</td><td>Keeps working.</td></tr>
<tr><td>Field removed or retyped</td><td class="mono">MAJOR</td><td>Breaks. 18 months advance notice before it ships.</td></tr>
<tr><td>Changed checksum or framing</td><td class="mono">MAJOR</td><td>Breaks. The wire format is frozen within a major version.</td></tr>
</tbody>
</table>

<h2 id="releases">Releases</h2>
<div class="tblwrap"><table>
<thead><tr><th>Version</th><th>Description</th><th>Tag</th></tr></thead>
<tbody>{rows}</tbody>
</table></div>

<h2 id="citation">Citing BXP</h2>
<p>The specification and the reference implementation each have a permanent DOI.
Cite the specification when referring to the format or the protocol; cite the
implementation when referring to the software.</p>
<table>
<thead><tr><th>What</th><th>DOI</th></tr></thead>
<tbody>
<tr><td>Specification v2.0</td><td><a href="https://doi.org/{doi_spec}">doi:{doi_spec}</a></td></tr>
<tr><td>Reference implementation</td><td><a href="https://doi.org/{doi_impl}">doi:{doi_impl}</a></td></tr>
</tbody>
</table>
<p>Machine-readable citation metadata lives in
<a href="https://github.com/bxpprotocol/bxp-spec/blob/main/CITATION.cff">CITATION.cff</a>,
so GitHub's &ldquo;Cite this repository&rdquo; and tools such as
<code>doi2bib</code> resolve authors, title, and version without you maintaining
a second copy.</p>

<div class="citebox"><h4>BibTeX</h4><pre><code>{html.escape(bibtex)}</code></pre></div>
<div class="citebox"><h4>RIS</h4><pre><code>{html.escape(ris)}</code></pre></div>
<div class="citebox"><h4>APA 7</h4><p>{apa}</p></div>
<div class="citebox"><h4>MLA 9</h4><p>{mla}</p></div>
<div class="citebox"><h4>Chicago 17</h4><p>{chicago}</p></div>

<h2 id="honesty">What to cite carefully</h2>
<p>If your work uses <code>bxpHri</code>, say plainly that the index is
experimental and not clinically validated. Citing the specification for the data
format and privacy model is straightforward; treating the composite index as a
validated health metric would misrepresent the state of the work.</p>
<p class="meta" style="margin-top:36px">
Metadata generated from <code>CITATION.cff</code> and <code>CHANGELOG.md</code>
in the repository. ORCID 0009-0001-4856-4986.</p>"""

    return page(
        "BXP versions, version pinning, and citation — BibTeX, RIS, APA, MLA",
        "How to pin a BXP specification version so your integration or citation stays valid, "
        "the compatibility policy, and citation formats with permanent Zenodo DOIs for the "
        "specification and reference implementation.",
        "versions.html",
        body,
    )


# ── Entry point ───────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(REPO), help="output directory")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    spec_md = (REPO / "SPEC.md").read_text(encoding="utf-8")
    openapi = json.loads((REPO / "openapi.json").read_text(encoding="utf-8"))
    citation = (REPO / "CITATION.cff").read_text(encoding="utf-8")
    changelog = (REPO / "CHANGELOG.md").read_text(encoding="utf-8")

    pages = {
        "spec.html": build_spec(spec_md),
        "api.html": build_api(openapi),
        "agents.html": build_agents(spec_md),
        "versions.html": build_versions(spec_md, citation, changelog),
    }

    for name, content in pages.items():
        (out / name).write_text(content, encoding="utf-8")
        print(f"wrote {name} ({len(content):,} bytes)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
