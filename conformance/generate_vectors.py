#!/usr/bin/env python3
"""
Generates the golden `.bxp` conformance vectors under conformance/vectors/
and the manifest.json describing what every implementation's decoder and
encoder must agree on (SPEC.md §15).

Regenerate with:
    python3 conformance/generate_vectors.py

This script is the single source of truth for the vectors — every vector
file and manifest entry below is produced from it, not hand-edited, so
provenance stays reproducible (SPEC.md §15.3). It only depends on the
Python reference encoder (sdk/python/bxp_binary.py), which is intentionally
the one implementation all others are checked against here.
"""
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "sdk" / "python"))

from bxp_binary import (  # noqa: E402
    encode_bxp_binary, HEADER_STRUCT, CHECKSUM_STRUCT, HEADER_SIZE,
)

VECTORS_DIR = Path(__file__).resolve().parent / "vectors"
VECTORS_DIR.mkdir(exist_ok=True)

MINIMAL_READING = {
    "bxpVersion": "2.0",
    "fileType": "reading",
    "deviceUuid": "550e8400-e29b-41d4-a716-446655440000",
    "geohash": "s1v0g",
    "timestampUs": 1710000000000000,
    "agents": [
        {"agentId": "PM2_5", "value": 47.3, "unit": "ug/m3"},
    ],
    "quality": {"flag": "UNVALIDATED"},
}

FULL_READING = {
    "bxpVersion": "2.0",
    "fileType": "reading",
    "deviceUuid": "550e8400-e29b-41d4-a716-446655440000",
    "geohash": "s1v0g",
    "latitude": 5.5571,
    "longitude": -0.1969,
    "altitudeM": 61.0,
    "timestampUs": 1710000000000000,
    "durationS": 60,
    "indoorOutdoor": "outdoor",
    "agents": [
        {
            "agentId": "PM2_5", "value": 47.3, "unit": "ug/m3",
            "uncertainty": 3.1, "method": "optical", "belowLod": False,
        },
        {
            "agentId": "CO", "value": 1.2, "unit": "ppm",
            "uncertainty": 0.1, "method": "electrochemical", "belowLod": False,
        },
    ],
    "context": {
        "temperatureC": 28.4, "humidityPct": 72.1,
        "pressureHpa": 1012.3, "windSpeedMs": 2.1, "windDirDeg": 220,
    },
    "quality": {
        "flag": "VALIDATED", "confidence": 0.94,
        "qcMethod": "automated-v2", "notes": "",
    },
    "signature": "",
}

FUTURE_MINOR_READING = dict(MINIMAL_READING, bxpVersion="2.99")
FUTURE_MINOR_READING["ext"] = {"org.example.mycompany": {"calibrationBatch": "B-2026-04"}}

UNSUPPORTED_MAJOR_READING = dict(MINIMAL_READING, bxpVersion="99.0")

AGGREGATE_RECORD = {
    "bxpVersion": "2.0", "fileType": "aggregate", "geohash": "s1v0g",
    "timestampUs": 1710000000000000,
    "period": "hourly",
    "agents": [{"agentId": "PM2_5", "mean": 44.1, "min": 12.0, "max": 88.7, "count": 12}],
}

DEVICE_RECORD = {
    "bxpVersion": "2.0", "fileType": "device",
    "deviceUuid": "550e8400-e29b-41d4-a716-446655440000",
    "timestampUs": 1710000000000000,
    "sourceType": "phone_app", "capabilities": ["PM2_5", "TEMP", "RH"],
    "accuracyClass": "tier1",
}

AGENT_RECORD = {
    "bxpVersion": "2.0", "fileType": "agent", "timestampUs": 1710000000000000,
    "agentId": "PM2_5", "unit": "ug/m3", "category": "particulates",
}

ALERT_RECORD = {
    "bxpVersion": "2.0", "fileType": "alert", "timestampUs": 1710000000000000,
    "geohash": "s1v0g", "level": "HIGH", "bxpHri": 68.2,
}

META_RECORD = {
    "bxpVersion": "2.0", "fileType": "meta", "timestampUs": 1710000000000000,
    "volumeId": "example-node-01", "schemaVersion": "2.0",
}


def _write(name, raw):
    (VECTORS_DIR / name).write_bytes(raw)
    return name


def _corrupt(raw: bytes, offset: int, xor: int = 0xFF) -> bytes:
    b = bytearray(raw)
    b[offset] ^= xor
    return bytes(b)


def build():
    manifest = {"vectors": []}

    # ---- Valid vectors -------------------------------------------------
    valid_specs = [
        ("minimal_reading.bxp", MINIMAL_READING, "reading", False),
        ("full_reading.bxp", FULL_READING, "reading", False),
        ("full_reading_compressed.bxp", FULL_READING, "reading", True),
        ("aggregate.bxp", AGGREGATE_RECORD, "aggregate", False),
        ("device.bxp", DEVICE_RECORD, "device", False),
        ("agent.bxp", AGENT_RECORD, "agent", False),
        ("alert.bxp", ALERT_RECORD, "alert", False),
        ("meta.bxp", META_RECORD, "meta", False),
        ("future_minor_version_with_ext.bxp", FUTURE_MINOR_READING, "reading", False),
    ]
    for filename, record, file_type, compress in valid_specs:
        raw = encode_bxp_binary(record, file_type=file_type, compress=compress,
                                 signed=False, draft=False)
        _write(filename, raw)
        manifest["vectors"].append({
            "file": filename,
            "expectValid": True,
            "expectMajorVersionSupported": record["bxpVersion"].split(".")[0] == "2",
            "fileType": file_type,
            "compressed": compress,
            "record": record,
        })

    # signed+draft flags together
    signed_draft_record = dict(MINIMAL_READING)
    raw = encode_bxp_binary(signed_draft_record, file_type="reading",
                             signed=True, draft=True)
    _write("signed_draft_flags.bxp", raw)
    manifest["vectors"].append({
        "file": "signed_draft_flags.bxp", "expectValid": True,
        "expectMajorVersionSupported": True,
        "fileType": "reading", "compressed": False,
        "expectFlags": {"compressed": False, "encrypted": False, "signed": True, "draft": True},
        "record": signed_draft_record,
    })

    # unsupported major version — decodes header fine, but MUST be
    # rejected by a conformant decoder when verify=True (SPEC.md §5.8)
    raw = encode_bxp_binary(UNSUPPORTED_MAJOR_READING, file_type="reading")
    _write("unsupported_major_version.bxp", raw)
    manifest["vectors"].append({
        "file": "unsupported_major_version.bxp", "expectValid": False,
        "expectMajorVersionSupported": False,
        "reason": "major version 99 is not supported major version 2",
        "record": UNSUPPORTED_MAJOR_READING,
    })

    # ---- Malformed vectors (derived by mutating a valid one) -----------
    base_raw = encode_bxp_binary(MINIMAL_READING, file_type="reading")

    bad_magic = _corrupt(base_raw, 0, 0xFF)
    _write("bad_magic.bxp", bad_magic)
    manifest["vectors"].append({
        "file": "bad_magic.bxp", "expectValid": False,
        "reason": "magic number corrupted",
    })

    truncated_header = base_raw[:10]
    _write("truncated_header.bxp", truncated_header)
    manifest["vectors"].append({
        "file": "truncated_header.bxp", "expectValid": False,
        "reason": "file shorter than the 32-byte fixed header",
    })

    truncated_payload = base_raw[:HEADER_SIZE + 3]
    _write("truncated_payload.bxp", truncated_payload)
    manifest["vectors"].append({
        "file": "truncated_payload.bxp", "expectValid": False,
        "reason": "payload shorter than the header's declared payload length",
    })

    # Header checksum lives at bytes 0x18-0x1B (first 4 bytes of the
    # checksum struct) - corrupt one of those bytes.
    bad_header_checksum = _corrupt(base_raw, HEADER_STRUCT.size + 1, 0xFF)
    _write("bad_header_checksum.bxp", bad_header_checksum)
    manifest["vectors"].append({
        "file": "bad_header_checksum.bxp", "expectValid": False,
        "reason": "header CRC32 does not match header bytes",
    })

    # Payload checksum lives at bytes 0x1C-0x1F (second 4 bytes of the
    # checksum struct).
    bad_payload_checksum = _corrupt(base_raw, HEADER_STRUCT.size + CHECKSUM_STRUCT.size - 1, 0xFF)
    _write("bad_payload_checksum.bxp", bad_payload_checksum)
    manifest["vectors"].append({
        "file": "bad_payload_checksum.bxp", "expectValid": False,
        "reason": "payload CRC32 does not match payload bytes",
    })

    # Corrupt a payload byte (well past the header) without touching either
    # checksum field, so the *payload* checksum itself catches it.
    corrupted_payload_byte = _corrupt(base_raw, HEADER_SIZE + 5, 0xFF)
    _write("corrupted_payload_byte.bxp", corrupted_payload_byte)
    manifest["vectors"].append({
        "file": "corrupted_payload_byte.bxp", "expectValid": False,
        "reason": "payload byte flipped after encoding; payload CRC32 mismatch",
    })

    manifest["headerSize"] = HEADER_SIZE
    manifest["magicHex"] = "0x42585000"
    manifest["supportedMajorVersion"] = 2

    (VECTORS_DIR.parent / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=False) + "\n"
    )
    print(f"Wrote {len(manifest['vectors'])} vectors to {VECTORS_DIR}")
    print(f"Wrote manifest to {VECTORS_DIR.parent / 'manifest.json'}")


if __name__ == "__main__":
    build()
