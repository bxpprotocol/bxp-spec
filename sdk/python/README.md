# bxp-sdk (Python)

Python SDK for **BXP — the Breathe Exposure Protocol**, an open data standard
for air-quality / atmospheric exposure readings. Zero required dependencies
(`httpx` is optional, for the async client).

```bash
pip install bxp-sdk            # once published; until then: pip install ./sdk/python
```

```python
from bxp_sdk import calculate_risk, write_bxp
from bxp_binary import encode_bxp_binary, decode_bxp_binary

# Compute the BXP Health Risk Index (0-100) for a set of readings
risk = calculate_risk(agents=[{"agentId": "PM2_5", "value": 47.3, "unit": "ug/m3"}])
print(risk["score"], risk["level"])

# Write a reading as JSON (.bxp.json) ...
record = write_bxp("reading.bxp.json", {
    "latitude": 5.6037, "longitude": -0.1870,
    "pm25": 47.3, "no2": 18.3,
})

# ... or as the compact binary container (.bxp)
raw = encode_bxp_binary(record, compress=True)
assert decode_bxp_binary(raw)["record"]["deviceUuid"] == record["deviceUuid"]
```

- Format and protocol specification: [`SPEC.md`](../../SPEC.md)
- Full project documentation: [repository README](../../README.md)
- Tests: `python -m pytest tests/`

Licensed under Apache-2.0.
