#!/usr/bin/env python3
"""
Conformance test for personal exposure records (SPEC §10.5).

Tests:
  1. createExposureEntry produces a valid entry with correct entryHash
  2. validateExposureEntry catches tampered entries (entryHash mismatch)
  3. validateExposureChain validates genesis and linked chains
  4. validateExposureChain rejects broken previousHash links
  5. appendToLedger creates/reads/appends to a .bxp.json ledger
  6. Python and TypeScript entryHash are byte-identical (see verify_exposure_ts.mjs)

Run with: python3 conformance/verify_exposure_python.py
"""
import json
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "sdk" / "python"))

from bxp_sdk import (  # noqa: E402
    createExposureEntry,
    validateExposureEntry,
    validateExposureChain,
    appendToLedger,
    readLedger,
    _entry_hash,
)

passed = failed = 0


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        print(f"  PASS  {name}")
        passed += 1
    else:
        print(f"  FAIL  {name} {detail}")
        failed += 1


# ── 1. Genesis entry creation ──
e1 = createExposureEntry(
    agents=[{"agentId": "PM2_5", "value": 47.2, "unit": "ug/m3"},
            {"agentId": "NO2",   "value": 18.3, "unit": "ug/m3"}],
    source="open-meteo",
    measurementType="modelled",
    location={"lat": 5.6037, "lon": -0.1870, "geohash": "s1v0gx4"},
    previousHash=None,
    locationPrecision="area",
    qualityNotes=["WHO 24h PM2.5 guideline (15 µg/m³) exceeded"],
    timestampUs=1710000000000000,
)
check("genesis entry has recordType=exposure", e1["recordType"] == "exposure")
check("genesis entry has entryHash", e1["entryHash"].startswith("sha256:"))
check("genesis entry previousHash is null", e1["previousHash"] is None)

# entryHash must be stable
e1_again = createExposureEntry(
    agents=[{"agentId": "PM2_5", "value": 47.2, "unit": "ug/m3"},
            {"agentId": "NO2",   "value": 18.3, "unit": "ug/m3"}],
    source="open-meteo",
    measurementType="modelled",
    location={"lat": 5.6037, "lon": -0.1870, "geohash": "s1v0gx4"},
    previousHash=None,
    locationPrecision="area",
    qualityNotes=["WHO 24h PM2.5 guideline (15 µg/m³) exceeded"],
    timestampUs=1710000000000000,
)
check("entryHash is deterministic", e1["entryHash"] == e1_again["entryHash"])

# ── 2. validateExposureEntry ──
r = validateExposureEntry(e1)
check("genesis entry validates", r["valid"], r["errors"])

# Tampered entry: flip a value
tampered = dict(e1)
tampered["agents"] = [dict(a) for a in e1["agents"]]
tampered["agents"][0]["value"] = 999.0
# Recompute hash to match tampered content (simulating an attacker who re-signs)
tampered["entryHash"] = _entry_hash(tampered)
check("tampered entry with re-computed hash still validates structure",
      validateExposureEntry(tampered)["valid"],
      "structure-only validation passes on re-signed tampered entry")

# Tampered entry: entryHash doesn't match content
tampered2 = dict(e1)
tampered2["agents"] = [dict(a) for a in e1["agents"]]
tampered2["agents"][0]["value"] = 999.0
# Don't recompute entryHash — it still has the old hash
check("tampered entry with stale entryHash is invalid",
      not validateExposureEntry(tampered2)["valid"])

# Missing required field
bad = dict(e1)
del bad["source"]
check("missing source field is invalid",
      not validateExposureEntry(bad)["valid"])

# Invalid source
bad2 = dict(e1)
bad2["source"] = "not-a-source"
check("invalid source is invalid",
      not validateExposureEntry(bad2)["valid"])

# ── 3. validateExposureChain ──
e2 = createExposureEntry(
    agents=[{"agentId": "PM2_5", "value": 30.1, "unit": "ug/m3"}],
    source="bxp-node",
    measurementType="measured",
    location={"lat": 5.6037, "lon": -0.1870, "geohash": "s1v0gx4"},
    previousHash=e1["entryHash"],
    locationPrecision="area",
    qualityNotes=[],
    timestampUs=1710000001000000,
)

chain = validateExposureChain([e1, e2])
check("two-entry chain validates", chain["valid"], chain["errors"])
check("chain entryCount is 2", chain["entryCount"] == 2)

# Broken chain: wrong previousHash
e2_broken = dict(e2)
e2_broken["previousHash"] = "sha256:deadbeef"
broken = validateExposureChain([e1, e2_broken])
check("broken previousHash detected", not broken["valid"])
check("firstBrokenIndex is 1", broken["firstBrokenIndex"] == 1)

# Non-genesis first entry with previousHash != null
e_genesis_wrong = dict(e1)
e_genesis_wrong["previousHash"] = "sha256:something"
bad_genesis = validateExposureChain([e_genesis_wrong])
check("non-null previousHash on genesis detected", not bad_genesis["valid"])

# Empty chain
empty = validateExposureChain([])
check("empty chain is invalid", not empty["valid"])

# ── 4. appendToLedger / readLedger ──
with tempfile.TemporaryDirectory() as td:
    ledger = Path(td) / "exposure.bxp.json"

    # First append creates the file
    result = appendToLedger(str(ledger), {
        "agents": [{"agentId": "PM2_5", "value": 47.2, "unit": "ug/m3"}],
        "source": "open-meteo",
        "measurementType": "modelled",
        "location": {"lat": 5.6037, "lon": -0.1870, "geohash": "s1v0gx4"},
        "locationPrecision": "area",
        "qualityNotes": ["PM2.5 above WHO guideline"],
    })
    check("appendToLedger creates ledger", result["valid"], result["errors"])
    check("ledger file exists", ledger.exists())

    # Read back
    read = readLedger(str(ledger))
    check("readLedger returns 1 entry", read["entryCount"] == 1)
    check("readLedger chainValid", read["chainValid"])

    # Second append chains to first
    result2 = appendToLedger(str(ledger), {
        "agents": [{"agentId": "PM2_5", "value": 30.1, "unit": "ug/m3"}],
        "source": "bxp-node",
        "measurementType": "measured",
        "location": {"lat": 5.6037, "lon": -0.1870, "geohash": "s1v0gx4"},
        "locationPrecision": "area",
    })
    check("second append succeeds", result2["valid"], result2["errors"])
    check("second entry previousHash matches first entryHash",
          result2["entry"]["previousHash"] == result["entry"]["entryHash"])

    # Read back both
    read2 = readLedger(str(ledger))
    check("readLedger returns 2 entries", read2["entryCount"] == 2)
    check("readLedger chainValid for 2 entries", read2["chainValid"])

    # Tamper with the ledger file directly
    data = json.loads(ledger.read_text())
    data[1]["agents"][0]["value"] = 999.0
    # Don't fix entryHash — it's now stale
    ledger.write_text(json.dumps(data, indent=2))
    read3 = readLedger(str(ledger))
    check("tampered ledger detected as invalid", not read3["chainValid"])

print(f"\n{passed} passed, {failed} failed (Python exposure conformance)")
sys.exit(0 if failed == 0 else 1)