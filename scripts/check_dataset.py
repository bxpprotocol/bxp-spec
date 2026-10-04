#!/usr/bin/env python3
"""Validate the published sample dataset against BXP's own validator.

This exists because the dataset did fail. When `source` became required in
SPEC.md 6.8, the SDK validator was updated but `datasets/sample_readings.bxp.json`
was not, so all ten records failed. That is the most damaging possible
inconsistency: the first file anyone copies did not satisfy the standard being
advertised.

It is also a useful general check. The dataset, the conformance vectors, and
the documentation samples should all agree with the validator at all times.

    python scripts/check_dataset.py

Exit code is non-zero on any failure, so CI can gate on it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "sdk" / "python"))


def main() -> int:
    from bxp_sdk import validate_bxp_record  # imported late so path insert applies

    path = REPO / "datasets" / "sample_readings.bxp.json"
    if not path.exists():
        print(f"FAIL  {path} does not exist")
        return 1

    doc = json.loads(path.read_text(encoding="utf-8"))
    readings = doc.get("readings")
    if not isinstance(readings, list) or not readings:
        print("FAIL  dataset has no readings array")
        return 1

    failures = 0
    for i, r in enumerate(readings):
        result = validate_bxp_record(r)
        errors = result.get("errors", [])
        if errors:
            failures += 1
            first = errors[0]
            print(f"FAIL  reading[{i}]: {first}")

    declared = doc.get("recordCount")
    if declared is not None and declared != len(readings):
        print(f"FAIL  recordCount says {declared} but the file holds {len(readings)}")
        failures += 1

    if failures:
        print(f"\n{failures} problem(s) in {path.name}")
        return 1

    # The dataset must also be honest about what it is. A demonstration fixture
    # presented as observational data is the provenance-laundering that
    # SPEC.md 5.5.1 and 6.8 exist to prevent.
    unlabelled = [i for i, r in enumerate(readings) if not r.get("source")]
    if unlabelled:
        print(f"FAIL  readings without a source classification: {unlabelled}")
        return 1

    kinds = sorted({r["source"] for r in readings})
    print(f"OK    {path.name}: {len(readings)} readings valid, source={kinds}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())