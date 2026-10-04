#!/usr/bin/env python3
"""Generate the data page: the sample dataset as a discoverable research artefact.

The dataset existed in the repository but was invisible to anyone not already
reading the source. Environmental-data work is dataset-first: people look for
data, not for protocols, and a dataset is what gets cited, mirrored, and cited
again.

This page publishes it with schema.org Dataset markup so it is eligible for
dataset search and for the data catalogues that index it. Content is read from
the dataset itself, so the field documentation cannot drift from the data.

    python scripts/build_data_page.py --out ../bxpprotocol.github.io
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from build_reference_pages import CSS  # noqa: E402  shared stylesheet, not duplicated

SITE = "https://bxpprotocol.github.io"

# Honest, reusable description of the format for Dataset markup.
DATASET_DESCRIPTION = (
    "Synthetic demonstration dataset of 10 atmospheric exposure records across "
    "major world cities, published in the BXP (.bxp.json) format. Illustrates "
    "the BXP record structure: geohash plus coordinates, per-agent measurements "
    "with canonical units, quality flags, and the experimental composite health "
    "risk index. Records are synthetic demonstration data, not measurements, and "
    "are marked source=simulated and quality.flag=UNVALIDATED."
)


def esc(s) -> str:
    return html.escape(str(s))


def build_dataset_ld(doc: dict) -> dict:
    """schema.org Dataset description for the sample dataset.

    Written to the page as JSON-LD and also emitted standalone as dataset.json,
    because data catalogues and harvesters fetch machine-readable dataset
    metadata rather than parsing HTML.
    """
    ld = {
        "@context": "https://schema.org",
        "@type": "Dataset",
        "name": doc.get("datasetName", "BXP Sample Dataset"),
        "alternateName": "BXP .bxp.json sample readings",
        "description": DATASET_DESCRIPTION,
        "url": f"{SITE}/data.html",
        "license": "https://www.apache.org/licenses/LICENSE-2.0",
        "isAccessibleForFree": True,
        "keywords": [
            "air quality data", "atmospheric exposure", "PM2.5", "air pollution",
            "environmental sensor data", "open data format", "BXP",
            "synthetic demonstration data",
        ],
        "creator": {
            "@type": "Organization",
            "name": "BXP Protocol contributors",
            "url": SITE,
        },
        "isPartOf": {
            "@type": "Dataset",
            "name": "BXP Global Air Quality Sample Dataset",
            "url": f"{SITE}/data.html",
        },
        "distribution": [
            {
                "@type": "DataDownload",
                "encodingFormat": "application/json",
                "contentURL": f"{SITE}/sample_readings.bxp.json",
                "encodingSchema": "https://github.com/bxpprotocol/bxp-spec/blob/main/SPEC.md",
                "description": (
                    "BXP .bxp.json records. Ten synthetic demonstration readings."
                ),
            },
            {
                "@type": "DataDownload",
                "encodingFormat": "application/json",
                "contentURL": "https://github.com/bxpprotocol/bxp-spec/blob/main/datasets/sample_readings.bxp.json",
                "description": "Same dataset in the source repository.",
            },
        ],
    }
    date_pub = str(doc.get("generatedAt", ""))
    if re.match(r"^\d{4}-\d{2}-\d{2}", date_pub):
        ld["datePublished"] = date_pub[:10]
        ld["dateModified"] = date_pub[:10]
    ld["version"] = str(doc.get("bxpVersion", "2.0"))
    ld["variableMeasured"] = [
        "pm25", "pm10", "no2", "o3", "so2", "co", "temperature", "humidity"
    ]
    return ld


def strip_md(md: str) -> str:
    out = []
    for line in md.split("\n"):
        line = re.sub(r"^#{1,6}\s+", "", line)
        line = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", line)
        line = re.sub(r"^\s*[-*]\s+", "- ", line)
        line = re.sub(r"^\|", "| ", line)
        line = re.sub(r"[*`]", "", line)
        out.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()


def build(doc: dict, spec_md: str) -> str:
    readings = doc.get("readings", [])

    # ---- schema.org Dataset markup -----------------------------------
    ld = build_dataset_ld(doc)
    ld_json = json.dumps(ld, indent=2, ensure_ascii=False)

    # ---- field inventory, derived from the data --------------------------
    agent_counter: Counter = Counter()
    units: dict[str, str] = {}
    for r in readings:
        for a in r.get("agents", []):
            aid = a.get("agentId", "?")
            agent_counter[aid] += 1
            units.setdefault(aid, a.get("unit", ""))

    # Which agents the spec weights into HRI, pulled from the spec itself.
    hri_agents: set[str] = set()
    m = re.search(
        r"Weighted agents[:\s*|]*([^\n]*(?:\n[^\n|]*\|?){0,12})", spec_md, re.I
    )
    if m:
        for token in re.findall(r"\b([A-Z][A-Z0-9_]{1,7})\b", m.group(1)):
            if token in units or token in agent_counter:
                hri_agents.add(token)
    if not hri_agents:
        hri_agents = {"PM2_5", "PM10", "NO2", "O3", "CO", "SO2", "TVOC"}

    agent_rows = "".join(
        f"<tr><td class='mono'>{esc(a)}</td>"
        f"<td class='mono'>{esc(units.get(a, ''))}</td>"
        f"<td>{esc('yes' if a in hri_agents else 'no')}</td>"
        f"<td>{esc(n)}</td></tr>"
        for a, n in sorted(agent_counter.items())
    )

    sample = readings[0] if readings else {}
    field_rows = []
    for key in ("bxpVersion", "source", "deviceUuid", "geohash", "latitude",
                "longitude", "timestampUs", "durationS", "indoorOutdoor",
                "agents", "context", "quality", "bxpHri", "bxpHriLevel"):
        if key in sample:
            val = sample[key]
            if isinstance(val, (list, dict)):
                shown = f"{type(val).__name__} ({len(val)})"
            else:
                shown = str(val)
            if len(shown) > 64:
                shown = shown[:61] + "…"
            field_rows.append(
                f"<tr><td class='mono'>{esc(key)}</td><td class='mono'>{esc(shown)}</td></tr>"
            )
    field_rows = "".join(field_rows)

    reading_rows = "".join(
        f"<tr><td class='mono'>{esc(r.get('geohash', ''))}</td>"
        f"<td class='mono'>{esc(r.get('latitude'))}, {esc(r.get('longitude'))}</td>"
        f"<td class='mono'>{esc(', '.join(a.get('agentId', '') for a in r.get('agents', [])))}</td>"
        f"<td class='mono'>{esc(r.get('bxpHri', '—'))}</td>"
        f"<td><span class='pill'>{esc(r.get('quality', {}).get('flag', ''))}</span></td></tr>"
        for r in readings
    )

    # ---- field dictionary from the specification -------------------------
    dict_rows = ""
    for agent_id, full_name in re.findall(
        r"^\|\s*(PM1|PM2_5|PM10|BC|CO|CO2|NO2|NO|SO2|O3|H2S|NH3|TVOC|BENZ|FORM|"
        r"TOLU|XYLE|NAPH|MOLD_S|POLL_G|POLL_T|BACT_T|DUST_M|PB|HG|AS|TEMP|RH|PRESS|UV)\s*\|\s*([^|]+?)\s*\|",
        spec_md,
        flags=re.M,
    ):
        if agent_id in agent_counter:
            dict_rows += (
                f"<tr><td class='mono'>{esc(agent_id)}</td><td>{esc(full_name)}</td></tr>"
            )
    if not dict_rows:
        dict_rows = "".join(
            f"<tr><td class='mono'>{esc(a)}</td><td>see specification Appendix A</td></tr>"
            for a in sorted(agent_counter)
        )

    body = f"""<span class="eyebrow">Data</span>
<h1>BXP sample dataset</h1>
<p class="lede">Ten atmospheric exposure records in the BXP format, covering
different agent combinations and quality flags. Published so integrators have
concrete input to test against, and so the format is legible to people who work
from data rather than from specifications.</p>

<div class="note"><strong>These are not measurements</strong>
Every record carries <code>source: "simulated"</code> and
<code>quality.flag: "UNVALIDATED"</code>. They exist to demonstrate the record
structure. Do not use them for analysis, reporting, or any health decision. The
classification is not decoration: <a href="spec.html">SPEC.md 6.8</a> requires
that provenance travel with the data, and a demonstration fixture presented as
observational data is exactly what that rule exists to prevent.</div>

<h2 id="download">Download</h2>
<table>
<thead><tr><th>File</th><th>Format</th><th>Records</th><th>Size</th></tr></thead>
<tbody>
<tr>
  <td><a href="sample_readings.bxp.json" download><code>sample_readings.bxp.json</code></a></td>
  <td>BXP JSON (application/json)</td>
  <td>{len(readings)}</td>
  <td class="mono">{(REPO / 'datasets' / 'sample_readings.bxp.json').stat().st_size:,} B</td>
</tr>
<tr>
  <td><a href="https://github.com/bxpprotocol/bxp-spec/blob/main/datasets/sample_readings.bxp.json">Repository copy</a></td>
  <td>BXP JSON</td>
  <td>{len(readings)}</td>
  <td class="mono">—</td>
</tr>
</tbody>
</table>
<p>Machine-readable metadata for this dataset is published separately as
<a href="dataset.json"><code>dataset.json</code></a> (schema.org
<code>Dataset</code>), which is what data catalogues and harvesters read.</p>
<p>Use it with <a href="validator.html">the validator</a> to confirm your own
records parse, or with the
<a href="https://github.com/bxpprotocol/bxp-spec/tree/main/sdk/python">Python SDK</a>:</p>
<pre><code>from bxp_sdk import read_bxp
doc = read_bxp("sample_readings.bxp.json")   # keys ending _ are verification helpers</code></pre>

<h2 id="records">Contents</h2>
<div class="tblwrap"><table>
<thead><tr><th>Geohash</th><th>Coordinates</th><th>Agents</th><th>HRI</th><th>Quality</th></tr></thead>
<tbody>{reading_rows}</tbody>
</table></div>

<h2 id="agents">Agents present</h2>
<p>Agents marked <em>HRI</em> contribute to the composite index; the others are
carried in the record and available to applications.</p>
<div class="tblwrap"><table>
<thead><tr><th>Agent ID</th><th>Unit</th><th>HRI</th><th>Records</th></tr></thead>
<tbody>{agent_rows}</tbody>
</table></div>

<h2 id="fields">Record structure</h2>
<p>The first record, abbreviated:</p>
<div class="tblwrap"><table>
<thead><tr><th>Field</th><th>Value</th></tr></thead>
<tbody>{field_rows}</tbody>
</table></div>

<h2 id="dictionary">Field dictionary</h2>
<p>Agent identifiers used in this dataset, with their full names from
<a href="spec.html">Appendix A of the specification</a>. The complete reference
for all 31 agents is on the <a href="agents.html">agent reference page</a>.</p>
<div class="tblwrap"><table>
<thead><tr><th>Agent ID</th><th>Name</th></tr></thead>
<tbody>{dict_rows}</tbody>
</table></div>

<h2 id="converting">Converting from other formats</h2>
<p>If your data is not already in BXP, start from the integration guide rather
than hand-mapping fields:</p>
<ul>
  <li><a href="https://github.com/bxpprotocol/bxp-spec/blob/main/integrations/openaq_import.py">OpenAQ v3 importer</a> — included in the repository, converts OpenAQ locations and measurements to valid BXP records while preserving source provenance.</li>
  <li><a href="https://github.com/bxpprotocol/bxp-spec/blob/main/integrations/mqtt_bridge.py">MQTT bridge</a> — subscribes to a broker topic and emits BXP records, for live sensor output.</li>
  <li><a href="https://github.com/bxpprotocol/bxp-spec/blob/main/BXP_Protocol.postman_collection.json">Postman collection</a> — ready-to-use requests against any BXP node.</li>
</ul>

<h2 id="licence">Licence and citation</h2>
<p>The dataset is released under Apache 2.0, the same licence as the
specification. Cite it via the specification DOI:</p>
<p class="mono">doi:10.5281/zenodo.18906812</p>
<p>Full citation formats are on the <a href="versions.html">versions and citation
page</a>.</p>"""

    css = """
.pill{display:inline-block;font-family:var(--mono);font-size:10.5px;font-weight:600;
padding:2px 8px;border-radius:999px;background:var(--bg-sub);border:1px solid var(--line);
color:var(--ink-3);letter-spacing:.03em}
td.mono,th.mono{font-family:var(--mono);font-size:12.5px}
"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>BXP sample dataset — 10 atmospheric exposure records in the BXP format</title>
<meta name="description" content="Downloadable BXP-format sample dataset: 10 synthetic atmospheric exposure records demonstrating the record structure, agent units, and quality flags. Apache 2.0, with schema.org Dataset metadata.">
<link rel="canonical" href="https://bxpprotocol.github.io/data.html">
<meta name="robots" content="index,follow,max-snippet:-1">
<meta property="og:type" content="article">
<meta property="og:url" content="https://bxpprotocol.github.io/data.html">
<meta property="og:site_name" content="BXP Protocol">
<meta property="og:title" content="BXP sample dataset — atmospheric exposure records">
<meta property="og:description" content="Ten synthetic BXP records across world cities. Downloadable, Apache 2.0, clearly labelled as demonstration data.">
<meta name="twitter:card" content="summary">
<meta name="twitter:title" content="BXP sample dataset">
<meta name="twitter:description" content="Atmospheric exposure records in the BXP format, downloadable.">
<link rel="alternate" type="text/plain" title="BXP machine-readable index (llms.txt)" href="https://bxpprotocol.github.io/llms.txt">
<link rel="alternate" type="application/ld+json" title="Dataset metadata (schema.org Dataset)" href="https://bxpprotocol.github.io/dataset.json">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
<style>{CSS}{css}</style>
<script type="application/ld+json">
{ld_json}
</script>
</head>
<body>
<header class="top"><div class="wrap">
  <a class="logo" href="/"><span>B</span>BXP</a>
  <nav>
    <a href="/">Overview</a>
    <a href="spec.html">Specification</a>
    <a href="api.html">API</a>
    <a href="agents.html">Agents</a>
    <a href="data.html">Data</a>
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(REPO))
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    doc = json.loads((REPO / "datasets" / "sample_readings.bxp.json").read_text(encoding="utf-8"))
    spec_md = (REPO / "SPEC.md").read_text(encoding="utf-8")

    page = build(doc, spec_md)
    (out / "data.html").write_text(page, encoding="utf-8")
    print(f"wrote data.html ({len(page):,} bytes, {len(doc.get('readings', []))} records)")

    # Standalone Dataset metadata. Data catalogues and harvesters fetch a
    # machine-readable record rather than parsing the HTML page.
    ld = build_dataset_ld(doc)
    ld_path = out / "dataset.json"
    ld_path.write_text(json.dumps(ld, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote dataset.json ({ld_path.stat().st_size:,} bytes, {doc.get('recordCount')} records)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())