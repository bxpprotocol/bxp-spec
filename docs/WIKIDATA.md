# BXP — Wikidata entity submission

Prepared for manual submission at <https://www.wikidata.org/wiki/Special:NewItem>.

This is a copy-paste worksheet, not a build artefact. Wikidata requires login
and human review, so it cannot be automated, and it should not be: an entity
about a project is a claim about that project, and the person best placed to
make that claim is you.

## Why this is the highest-leverage single action

Wikidata is the one surface every other discovery system reads. Google, Bing,
Perplexity, Gemini and ChatGPT all resolve entities through it. A populated item
is what makes `BXP` stop being an ambiguous string that an assistant has to
guess at. One item, and every answer, knowledge panel, and generated citation
anywhere inherits the resolution, for free and permanently.

Right now `BXP` is not in Wikidata. An assistant asked "what is BXP" has no
anchor and will either conflate it with something else or decline to answer.

---

## Item 1 — the standard

| Field | Value | Wikidata type |
|---|---|---|
| **English label** | `BXP` | monolingual |
| **English description** | `open protocol and REST API for atmospheric exposure data interoperability` | monolingual |
| **Aliases (English)** | `Breathe Exposure Protocol` · `BXP Protocol` | monolingual |
| **instance of** | *file format* (Q1462124) | wikitable |
| | *open standard* (Q394979) | wikitable |
| | *application programming interface* (Q2934214) | wikitable |
| | *specification* (Q1301371) | wikitable |
| **official website** | https://bxpprotocol.github.io/ | URL |
| **documentation URL** | https://github.com/bxpprotocol/bxp-spec/blob/main/SPEC.md | URL |
| **source code repository** | https://github.com/bxpprotocol/bxp-spec | URL |
| **license** | Apache License 2.0 (Q111460) | wikitable |
| **copyright status** | copyrighted (Q50423863) | wikitable |
| **DOI (specification)** | 10.5281/zenodo.18906812 | external identifier |
| **DOI (implementation)** | 10.5281/zenodo.18907003 | external identifier |
| **ORCID** | 0009-0001-4856-4986 | external identifier |
| **GitHub username** | `bxpprotocol` | external identifier |
| **inception** | 2026-01-01 | point in time |
| **maintained by** | *Elvarin* (create or link the person item, Item 2) | wikitable |
| **has quality** | *experimental* (Q1969448) — applies to the health index only | wikitable |
| **described by URL** | https://bxpprotocol.github.io/llms.txt | URL |

**Statements about the subject matter** (what a standards item should say):

| Property | Value | Note |
|---|---|---|
| **has part(s)** | file format `.bxp` | the binary container |
| | file format `.bxp.json` | the JSON representation |
| | REST API `/bxp/v2/` | 23 operations |
| | BXP-HRI | **mark experimental** |
| **field of work** | atmospheric science | |
| | environmental monitoring | |
| | air quality | |
| | data interoperability | |
| **different from** | OpenAQ | cite SPEC.md §14 — a gateway, not a standard |
| | US EPA AQI | distinct derivation, cite WHO AQG 2021 |
| | OGC SensorThings API | compatibility, cite SPEC.md §14 |
| **compatible with / cites** | WHO Air Quality Guidelines 2021 | Q109424943 |
| | HL7 FHIR R4 | cite SPEC.md §14 |

**Description must carry the caveat.** Suggested text:

> An open protocol and REST API for atmospheric exposure data. Defines the `.bxp`
> binary container and an equivalent JSON representation, a 23-operation REST
> API, a five-stage processing pipeline, a privacy floor, and pull-based
> federation. Its composite health risk index (BXP-HRI) is experimental and is
> not clinically validated.

---

## Item 2 — the maintainer

| Field | Value |
|---|---|
| **English label** | `Elvarin` |
| **English description** | `maintainer of the BXP protocol` |
| **ORCID** | `0009-0001-4856-4986` |
| **GitHub username** | `bxpprotocol` |
| **website** | https://bxpprotocol.github.io/ |

Link `Item 1 → maintained by → Item 2`. A standards item with no linked author
is materially less likely to be trusted or reused.

---

## Item 3 — the protocol stages

Optional, but this is what turns a name into a concept other projects can
reference. Create these as subclasses of `Item 1` only if you later implement
them independently; otherwise list them in the Item 1 description.

| Label | Description |
|---|---|
| `BXP Locate stage` | resolves coordinates to a geohash cell with a documented precision floor |
| `BXP Detect stage` | tiers the source and classifies its provenance |
| `BXP Interpret stage` | normalises units, applies quality control, records corrections |
| `BXP Protect stage` | enforces the privacy floor: hashed identifiers, coarsened location, k-anonymity |
| `BXP Report stage` | stores, queries, and replicates the record across nodes |

---

## References — attach these, do not submit unsourced

Wikidata requires a reference for every statement. Use these.

| # | Property | Reference |
|---|---|---|
| R1 | official website, repository, DOI, licence | https://github.com/bxpprotocol/bxp-spec — retrieved 2026-10-04 |
| R2 | specification text | SPEC.md v2.0, https://doi.org/10.5281/zenodo.18906812 |
| R3 | REST API contract | https://bxpprotocol.github.io/openapi.json — OpenAPI 3.1, 23 paths |
| R4 | agent count (31) and WHO thresholds | SPEC.md Appendix A; WHO Air Quality Guidelines 2021, ISBN 978-92-4-0034228 |
| R5 | conformance model (17 vectors) | https://github.com/bxpprotocol/bxp-spec/tree/main/conformance/vectors |
| R6 | HRI is experimental and not validated | SPEC.md §13 — cite this specifically wherever HRI appears |
| R7 | compatibility claims | SPEC.md §14 |
| R8 | provenance / identity | https://github.com/bxpprotocol/bxp-spec/blob/main/GOVERNANCE.md |

Use `stated in`, `retrieved`, `publication date`, `author` or `ORCID` as the
reference type depending on the statement.

---

## Query it once created

Confirm the item resolves and is coherent:

```sparql
SELECT ?item ?itemLabel ?website ?doi ?license WHERE {
  VALUES ?item { wd:Q… }
  OPTIONAL { ?item wdt:P856 ?website }
  OPTIONAL { ?item wdt:P356 ?doi }
  OPTIONAL { ?item wdt:P275 ?license }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
}
```

Run at <https://query.wikidata.org/>.

Then check the downstream effect: Google's knowledge panel and the AI assistants
ingest Wikidata on their own schedule, so allow days to weeks before expecting
any visible change. Nothing else needs doing — this is a set-and-compound asset.

---

## After Wikidata: the DOI metadata

Both Zenodo records already exist, but their metadata drives ingestion into
DataCite, OpenAIRE, OpenAlex, Semantic Scholar, and Google Scholar. On each Zenodo
record, confirm:

| Field | Value |
|---|---|
| Creators | Elvarin, **with ORCID 0009-0001-4856-4986** |
| Related identifier | `IsSupplementTo` or `IsVersionOf` → the other DOI |
| Related identifier | `IsIdenticalTo` → the GitHub tag `v2.1.0` |
| Subjects | air quality, environmental monitoring, data interoperability, open standard, PM2.5 |
| Description | matches the Wikidata description above |
| Keywords | atmospheric exposure, air pollution, sensor interoperability |
| Version | 2.1.0 |

Zenodo is operated by DataCite, so a complete Zenodo record propagates
automatically to every downstream index. That is why fixing the metadata there
is higher value than registering the dataset a second time elsewhere.