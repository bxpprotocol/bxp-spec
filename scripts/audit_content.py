"""Stranger-check the generated pages: does each one answer a real question?

Structural validity is not usefulness. This asserts the substance is present,
so a page cannot pass by rendering an empty table or a broken template.
"""

import re
from pathlib import Path

SITE = Path(r"C:\Users\Aeron\bxpprotocol.github.io")

checks = [
    ("data.html", [
        ("names the dataset", r"schema\.org|application/ld\+json"),
        ("carries Dataset markup", r'"@type"\s*:\s*"Dataset"'),
        ("links the download", r'href="sample_readings\.bxp\.json"'),
        ("warns it is not measurement", r"not measurements|not observational|simulated"),
        ("documents record structure", r"bxpHriLevel|deviceUuid"),
        ("lists agents present", r"PM2_5"),
    ]),
    ("spec.html", [
        ("renders the abstract", r'id="1-abstract"'),
        ("renders the file format section", r'id="5-the-bxp-file-format"'),
        ("renders source classification", r'id="6-8-source-classification"'),
        ("renders the privacy framework", r'id="9-security-privacy-framework"'),
        ("renders conformance", r'id="15-conformance-test-vectors"'),
        ("renders the agent appendix", r'id="appendix-a-complete-agent-reference"'),
        ("has a table of contents", r"Table of Contents|Contents"),
    ]),
    ("api.html", [
        ("documents readings", r"/bxp/v2/readings"),
        ("documents nearby", r"/bxp/v2/nearby"),
        ("documents sync", r"/bxp/v2/sync"),
        ("documents health", r"/bxp/v2/health"),
        ("explains versioning", r"Version negotiation|version"),
    ]),
    ("agents.html", [
        ("lists PM2_5", r"PM2_5"),
        ("lists a heavy metal", r"\bPB\b"),
        ("explains units", r"[Uu]nit"),
        ("carries the HRI caveat", r"experimental"),
    ]),
    ("versions.html", [
        ("gives BibTeX", r"@software"),
        ("gives APA", r"APA"),
        ("gives RIS", r"TY\s+-\s+SOFT"),
        ("states the pinning rationale", r"[Pp]in"),
        ("carries the spec DOI", r"10\.5281/zenodo\.18906812"),
    ]),
    ("404.html", [
        ("offers a way back", r'href="/"'),
        ("lists the main surfaces", r"spec\.html|api\.html"),
        ("is noindex", r"noindex"),
    ]),
]

files = [
    ("llms-full.txt", [
        ("contains the spec", r"\.bxp File Format|BXP Technical Specification"),
        ("contains the API docs", r"REST|/bxp/v2/"),
        ("carries the HRI caveat", r"experimental"),
    ]),
    ("openapi.json", [
        ("declares OpenAPI 3.1", r'"openapi"\s*:\s*"3\.1'),
        ("has the readings path", r"/bxp/v2/readings"),
        ("declares the licence", r"Apache"),
    ]),
    ("sample_readings.bxp.json", [
        ("has readings", r'"readings"'),
        ("declares source", r'"source"'),
    ]),
]

bad = 0

print("HTML pages")
for name, reqs in checks:
    p = SITE / name
    if not p.exists():
        print(f"FAIL  {name}: missing")
        bad += 1
        continue
    text = p.read_text(encoding="utf-8", errors="replace")
    missing = [label for label, pat in reqs if not re.search(pat, text)]
    if missing:
        print(f"FAIL  {name}: {', '.join(missing)}")
        bad += 1
    else:
        print(f"OK    {name} ({len(text):,} bytes, {len(reqs)} checks)")

print()
print("Machine-readable artefacts")
for name, reqs in files:
    p = SITE / name
    if not p.exists():
        print(f"FAIL  {name}: missing")
        bad += 1
        continue
    text = p.read_text(encoding="utf-8", errors="replace")
    missing = [label for label, pat in reqs if not re.search(pat, text)]
    if missing:
        print(f"FAIL  {name}: {', '.join(missing)}")
        bad += 1
    else:
        print(f"OK    {name} ({len(text):,} bytes, {len(reqs)} checks)")

print()
raise SystemExit(1 if bad else 0)