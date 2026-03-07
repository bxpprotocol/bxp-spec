"""
BXP Example — Read .bxp files

This example shows how to read, validate, and analyze BXP files.

Run:
    cd bxp-protocol
    python examples/example_generate.py   # generate files first
    python examples/example_read.py
"""

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "sdk" / "python"))
from bxp_sdk import read_bxp, validate_bxp, calculate_risk

print("=" * 60)
print("  BXP Example — Reading .bxp files")
print("=" * 60)

# ─────────────────────────────────────────────────────────────
# Example 1: Read a generated file
# ─────────────────────────────────────────────────────────────

# Generate a file to read if it doesn't exist
if not Path("accra_central.bxp.json").exists():
    sys.path.insert(0, str(Path(__file__).parent))
    from bxp_sdk import write_bxp
    write_bxp("accra_central.bxp.json", {
        "latitude": 5.6037, "longitude": -0.1870,
        "pm25": 47.2, "pm10": 62.1, "no2": 18.3,
        "o3": 12.0, "temp": 29.0, "humidity": 78.0,
    })

print("\n[1] Reading accra_central.bxp.json")
record = read_bxp("accra_central.bxp.json")

print(f"  BXP Version:  {record['bxpVersion']}")
print(f"  Geohash:      {record['geohash']}")
print(f"  Agents:       {len(record['agents'])}")
print(f"  BXP_HRI:      {record['bxpHri']} [{record['bxpHriLevel']}]")
print(f"  Integrity:    {'✓ OK' if record['_integrityOk'] else '✗ FAILED'}")

# ─────────────────────────────────────────────────────────────
# Example 2: Read the sample dataset
# ─────────────────────────────────────────────────────────────
print("\n[2] Reading sample dataset")

dataset_path = Path(__file__).parent.parent / "datasets" / "sample_readings.bxp.json"
dataset = json.loads(dataset_path.read_text())

readings = dataset["readings"]
print(f"  Dataset:  {dataset['datasetName']}")
print(f"  Records:  {dataset['recordCount']}")
print()
print(f"  {'Location':<30} {'PM2.5':>7} {'NO2':>6} {'HRI':>6} Level")
print("  " + "-" * 60)

for r in readings:
    loc  = r["context"]["location"]
    pm25 = next((a["value"] for a in r["agents"]
                 if a["agentId"] == "PM2_5"), "?")
    no2  = next((a["value"] for a in r["agents"]
                 if a["agentId"] == "NO2"), "?")
    hri  = r["bxpHri"]
    lvl  = r["bxpHriLevel"]
    print(f"  {loc:<30} {str(pm25):>7} {str(no2):>6} {str(hri):>6} {lvl}")

# ─────────────────────────────────────────────────────────────
# Example 3: Validate a file
# ─────────────────────────────────────────────────────────────
print("\n[3] Validating accra_central.bxp.json")

result = validate_bxp("accra_central.bxp.json")
print(f"  Result:   {'✓ VALID' if result['valid'] else '✗ INVALID'}")
print(f"  Summary:  {result['summary']}")
if result["errors"]:
    for e in result["errors"]:
        print(f"    Error: {e}")
if result["warnings"]:
    for w in result["warnings"]:
        print(f"    Warning: {w}")

# ─────────────────────────────────────────────────────────────
# Example 4: Analyze the dataset
# ─────────────────────────────────────────────────────────────
print("\n[4] Dataset analysis")

hri_scores = [r["bxpHri"] for r in readings]
pm25_values = [
    a["value"] for r in readings
    for a in r["agents"] if a["agentId"] == "PM2_5"
]

print(f"  Average BXP_HRI:  {sum(hri_scores)/len(hri_scores):.1f}")
print(f"  Max BXP_HRI:      {max(hri_scores)} [{readings[hri_scores.index(max(hri_scores))]['context']['location']}]")
print(f"  Min BXP_HRI:      {min(hri_scores)} [{readings[hri_scores.index(min(hri_scores))]['context']['location']}]")
print(f"  Avg PM2.5:        {sum(pm25_values)/len(pm25_values):.1f} μg/m³  (WHO limit: 15)")
print(f"  Max PM2.5:        {max(pm25_values)} μg/m³")
print()

# Count by level
from collections import Counter
levels = Counter(r["bxpHriLevel"] for r in readings)
print(f"  Risk level distribution:")
for level, count in sorted(levels.items()):
    bar = "█" * count
    print(f"    {level:<12} {bar} ({count})")

print()
