"""
BXP Example — Generate .bxp files
Global cities demonstration.

Run:
    cd bxp-protocol
    python examples/example_generate.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "sdk" / "python"))
from bxp_sdk import write_bxp, calculate_risk

print("=" * 60)
print("  BXP Example — Generating .bxp files")
print("  Global cities demonstration")
print("=" * 60)

# ─────────────────────────────────────────────────────────────
# Example 1: Delhi — HAZARDOUS
# ─────────────────────────────────────────────────────────────
print("\n[1] Delhi, India — HAZARDOUS pollution event")

record = write_bxp("delhi_india.bxp.json", {
    "latitude":  28.6139,
    "longitude": 77.2090,
    "pm25":  156.3,
    "pm10":  228.4,
    "no2":   67.8,
    "o3":    5.1,
    "temp":  22.0,
    "humidity": 45.0,
    "context": {
        "location":    "Delhi, India",
        "country":     "IN",
        "nearbySource": "vehicles_crop_burning"
    }
})

print(f"  File:      delhi_india.bxp.json")
print(f"  Geohash:   {record['geohash']}")
print(f"  PM2.5:     {record['agents'][0]['value']} μg/m³  (WHO limit: 15)")
print(f"  BXP_HRI:   {record['bxpHri']} [{record['bxpHriLevel']}]")

# ─────────────────────────────────────────────────────────────
# Example 2: London — MODERATE
# ─────────────────────────────────────────────────────────────
print("\n[2] London, United Kingdom — MODERATE")

record2 = write_bxp("london_uk.bxp.json", {
    "latitude":  51.5074,
    "longitude": -0.1278,
    "pm25":  14.2,
    "pm10":  22.8,
    "no2":   38.1,
    "o3":    44.2,
    "temp":  12.0,
    "humidity": 72.0,
    "context": {
        "location": "London, United Kingdom",
        "country":  "GB",
        "nearbySource": "traffic_diesel"
    }
})

print(f"  File:      london_uk.bxp.json")
print(f"  PM2.5:     {record2['agents'][0]['value']} μg/m³")
print(f"  NO2:       {record2['agents'][2]['value']} ppb  (WHO limit: 25)")
print(f"  BXP_HRI:   {record2['bxpHri']} [{record2['bxpHriLevel']}]")

# ─────────────────────────────────────────────────────────────
# Example 3: Cairo — HAZARDOUS (desert dust)
# ─────────────────────────────────────────────────────────────
print("\n[3] Cairo, Egypt — HAZARDOUS (desert dust + traffic)")

record3 = write_bxp("cairo_egypt.bxp.json", {
    "latitude":  30.0444,
    "longitude": 31.2357,
    "pm25":  93.4,
    "pm10":  187.3,
    "no2":   49.2,
    "o3":    7.8,
    "temp":  28.0,
    "humidity": 35.0,
    "context": {
        "location": "Cairo, Egypt",
        "country":  "EG",
        "nearbySource": "desert_dust_traffic"
    }
})

print(f"  File:      cairo_egypt.bxp.json")
print(f"  PM10:      {record3['agents'][1]['value']} μg/m³  (WHO limit: 45)")
print(f"  BXP_HRI:   {record3['bxpHri']} [{record3['bxpHriLevel']}]")

# ─────────────────────────────────────────────────────────────
# Example 4: New York — MODERATE (clean comparison)
# ─────────────────────────────────────────────────────────────
print("\n[4] New York, USA — MODERATE (comparison)")

record4 = write_bxp("new_york_usa.bxp.json", {
    "latitude":  40.7128,
    "longitude": -74.0060,
    "pm25":  12.1,
    "pm10":  18.4,
    "no2":   29.6,
    "o3":    52.3,
    "temp":  18.0,
    "humidity": 61.0,
    "context": {
        "location": "New York, USA",
        "country":  "US",
        "nearbySource": "traffic_urban"
    }
})

print(f"  File:      new_york_usa.bxp.json")
print(f"  PM2.5:     {record4['agents'][0]['value']} μg/m³  ← within WHO limit")
print(f"  BXP_HRI:   {record4['bxpHri']} [{record4['bxpHriLevel']}]")

# ─────────────────────────────────────────────────────────────
# Example 5: Global comparison
# ─────────────────────────────────────────────────────────────
print("\n[5] Global risk comparison")
print()
print(f"  {'City':<30} {'PM2.5':>7}  {'BXP_HRI':>8}  Level")
print("  " + "-" * 58)

cities = [
    ("New York, USA",          12.1,  record4['bxpHri'],  record4['bxpHriLevel']),
    ("London, UK",             14.2,  record2['bxpHri'],  record2['bxpHriLevel']),
    ("Accra, Ghana",           47.2,  None,               None),
    ("Nairobi, Kenya",         38.9,  None,               None),
    ("Lagos, Nigeria",         68.4,  None,               None),
    ("Jakarta, Indonesia",     71.3,  None,               None),
    ("Cairo, Egypt",           93.4,  record3['bxpHri'],  record3['bxpHriLevel']),
    ("Beijing, China",         89.7,  None,               None),
    ("Delhi, India",          156.3,  record['bxpHri'],   record['bxpHriLevel']),
]

for city, pm25, hri, level in cities:
    if hri is None:
        r = calculate_risk(pm25=pm25)
        hri   = r['score']
        level = r['level']
    print(f"  {city:<30} {str(pm25):>7}  {str(hri):>8}  {level}")

print()
print("  Files generated:")
print("    delhi_india.bxp.json")
print("    london_uk.bxp.json")
print("    cairo_egypt.bxp.json")
print("    new_york_usa.bxp.json")
print()
print("  WHO PM2.5 annual limit: 5 μg/m³ | 24h limit: 15 μg/m³")
print("  Every city in this dataset exceeds the annual limit.")
print()
