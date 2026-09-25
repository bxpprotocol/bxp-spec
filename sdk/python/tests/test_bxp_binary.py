"""
Unit tests for bxp_binary.py — the binary .bxp container format
(spec SPEC.md section 5.1-5.2).

Run with:
    cd sdk/python && python -m pytest tests/ -v
or, with no pytest installed:
    cd sdk/python && python tests/test_bxp_binary.py
"""

import gzip
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from bxp_binary import (
    MAGIC, HEADER_SIZE, FILE_TYPES,
    FLAG_COMPRESSED, FLAG_ENCRYPTED, FLAG_SIGNED, FLAG_DRAFT,
    encode_bxp_binary, decode_bxp_binary, BXPBinaryError,
    bxp_json_to_binary, bxp_binary_to_json,
)


SAMPLE_RECORD = {
    "bxpVersion": "2.0",
    "deviceUuid": "550e8400-e29b-41d4-a716-446655440000",
    "geohash": "s1v0g",
    "latitude": 5.5571,
    "longitude": -0.1969,
    "timestampUs": 1710000000000000,
    "durationS": 60,
    "indoorOutdoor": "outdoor",
    "agents": [
        {"agentId": "PM2_5", "value": 47.3, "unit": "ug/m3"},
        {"agentId": "CO", "value": 1.2, "unit": "ppm"},
    ],
    "quality": {"flag": "VALIDATED", "confidence": 0.94},
}


# ── Header layout ──────────────────────────────────────────────

def test_header_is_32_bytes():
    raw = encode_bxp_binary(SAMPLE_RECORD)
    assert HEADER_SIZE == 32
    assert len(raw) >= 32


def test_magic_number_matches_spec():
    # Spec: 0x42585000 ("BXP\0")
    assert MAGIC == 0x42585000
    raw = encode_bxp_binary(SAMPLE_RECORD)
    assert raw[0:4] == bytes([0x42, 0x58, 0x50, 0x00])


def test_version_fields_default_to_record_bxpversion():
    raw = encode_bxp_binary(SAMPLE_RECORD)  # bxpVersion "2.0"
    decoded = decode_bxp_binary(raw)
    assert decoded["header"]["majorVersion"] == 2
    assert decoded["header"]["minorVersion"] == 0


def test_version_fields_parse_nonzero_minor():
    record = dict(SAMPLE_RECORD, bxpVersion="3.7")
    raw = encode_bxp_binary(record)
    decoded = decode_bxp_binary(raw)
    assert decoded["header"]["majorVersion"] == 3
    assert decoded["header"]["minorVersion"] == 7


@pytest.mark.parametrize("file_type,code", list(FILE_TYPES.items()))
def test_file_type_codes_match_spec_table(file_type, code):
    # Spec table: 0x01=reading 0x02=aggregate 0x03=agent 0x04=device 0x05=alert 0x06=meta
    raw = encode_bxp_binary(SAMPLE_RECORD, file_type=file_type)
    assert raw[8] == code
    decoded = decode_bxp_binary(raw)
    assert decoded["header"]["fileType"] == file_type


def test_reading_file_type_code_is_0x01():
    raw = encode_bxp_binary(SAMPLE_RECORD, file_type="reading")
    assert raw[8] == 0x01


def test_reserved_bytes_are_zero():
    raw = encode_bxp_binary(SAMPLE_RECORD)
    assert raw[0x0A:0x0C] == b"\x00\x00"


def test_timestamp_round_trips():
    raw = encode_bxp_binary(SAMPLE_RECORD)
    decoded = decode_bxp_binary(raw)
    assert decoded["header"]["timestampUs"] == SAMPLE_RECORD["timestampUs"]


def test_payload_length_field_matches_actual_payload():
    raw = encode_bxp_binary(SAMPLE_RECORD, compress=False)
    decoded = decode_bxp_binary(raw)
    payload = raw[HEADER_SIZE:]
    assert decoded["header"]["payloadLength"] == len(payload)


# ── Flags ───────────────────────────────────────────────────────

def test_uncompressed_flag_clear():
    raw = encode_bxp_binary(SAMPLE_RECORD, compress=False)
    flags_byte = raw[9]
    assert not (flags_byte & FLAG_COMPRESSED)


def test_compressed_flag_set_and_payload_is_gzip():
    raw = encode_bxp_binary(SAMPLE_RECORD, compress=True)
    flags_byte = raw[9]
    assert flags_byte & FLAG_COMPRESSED
    payload = raw[HEADER_SIZE:]
    # gzip magic bytes
    assert payload[:2] == b"\x1f\x8b"
    assert gzip.decompress(payload)  # doesn't raise


def test_signed_and_draft_flags():
    raw = encode_bxp_binary(SAMPLE_RECORD, signed=True, draft=True)
    decoded = decode_bxp_binary(raw)
    assert decoded["header"]["flags"]["signed"] is True
    assert decoded["header"]["flags"]["draft"] is True
    assert decoded["header"]["flags"]["compressed"] is False
    assert decoded["header"]["flags"]["encrypted"] is False


def test_encryption_not_implemented():
    with pytest.raises(NotImplementedError):
        encode_bxp_binary(SAMPLE_RECORD, encrypt=True)


# ── Round trip / lossless conversion (spec 5.1 requirement) ────

def test_round_trip_uncompressed_is_lossless():
    raw = encode_bxp_binary(SAMPLE_RECORD, compress=False)
    decoded = decode_bxp_binary(raw)
    assert decoded["record"] == SAMPLE_RECORD


def test_round_trip_compressed_is_lossless():
    raw = encode_bxp_binary(SAMPLE_RECORD, compress=True)
    decoded = decode_bxp_binary(raw)
    assert decoded["record"] == SAMPLE_RECORD


def test_compressed_is_smaller_than_uncompressed_for_typical_reading():
    raw_plain = encode_bxp_binary(SAMPLE_RECORD, compress=False)
    raw_gzip = encode_bxp_binary(SAMPLE_RECORD, compress=True)
    assert len(raw_gzip) < len(raw_plain)


def test_binary_is_smaller_than_equivalent_pretty_json():
    pretty_json = json.dumps(SAMPLE_RECORD, indent=2).encode("utf-8")
    raw = encode_bxp_binary(SAMPLE_RECORD, compress=True)
    assert len(raw) < len(pretty_json)


# ── Checksums / integrity (spec's own verification intent) ─────

def test_header_checksum_ok_flag_true_for_untampered_file():
    raw = encode_bxp_binary(SAMPLE_RECORD)
    decoded = decode_bxp_binary(raw)
    assert decoded["headerChecksumOk"] is True
    assert decoded["payloadChecksumOk"] is True


def test_tampered_payload_byte_is_detected():
    raw = bytearray(encode_bxp_binary(SAMPLE_RECORD))
    raw[-1] ^= 0xFF  # flip a bit in the payload
    with pytest.raises(BXPBinaryError):
        decode_bxp_binary(bytes(raw))


def test_tampered_payload_byte_detected_without_raising_when_verify_false():
    raw = bytearray(encode_bxp_binary(SAMPLE_RECORD, compress=False))
    # Flip an ASCII digit inside the JSON payload so it stays valid,
    # parseable JSON but no longer matches the stored checksum.
    payload_start = HEADER_SIZE
    digit_offset = raw[payload_start:].index(b"4")  # first '4' in e.g. "47.3"
    raw[payload_start + digit_offset] = ord("9")
    decoded = decode_bxp_binary(bytes(raw), verify=False)
    assert decoded["payloadChecksumOk"] is False


def test_tampered_header_byte_is_detected():
    raw = bytearray(encode_bxp_binary(SAMPLE_RECORD))
    raw[5] ^= 0xFF  # inside the header-checksummed region
    with pytest.raises(BXPBinaryError):
        decode_bxp_binary(bytes(raw))


def test_truncated_payload_is_detected():
    raw = encode_bxp_binary(SAMPLE_RECORD)
    with pytest.raises(BXPBinaryError):
        decode_bxp_binary(raw[:-5])


def test_bad_magic_number_rejected():
    raw = bytearray(encode_bxp_binary(SAMPLE_RECORD))
    raw[0:4] = b"\x00\x00\x00\x00"
    with pytest.raises(BXPBinaryError):
        decode_bxp_binary(bytes(raw))


def test_too_short_file_rejected():
    with pytest.raises(BXPBinaryError):
        decode_bxp_binary(b"\x00" * 10)


def test_unknown_file_type_rejected():
    with pytest.raises(ValueError):
        encode_bxp_binary(SAMPLE_RECORD, file_type="not_a_real_type")


# ── File-based conversion helpers ───────────────────────────────

def test_json_to_binary_and_back_file_round_trip(tmp_path):
    json_path = tmp_path / "reading.bxp.json"
    bin_path = tmp_path / "reading.bxp"
    back_path = tmp_path / "reading_back.bxp.json"

    json_path.write_text(json.dumps(SAMPLE_RECORD), encoding="utf-8")
    bxp_json_to_binary(json_path, bin_path, compress=True)
    assert bin_path.exists()
    assert bin_path.read_bytes()[:4] == bytes([0x42, 0x58, 0x50, 0x00])

    record_back = bxp_binary_to_json(bin_path, back_path)
    assert record_back == SAMPLE_RECORD
    assert json.loads(back_path.read_text()) == SAMPLE_RECORD


if __name__ == "__main__":
    # Allow running without pytest installed, as a plain smoke test.
    import traceback
    tests = [(k, v) for k, v in list(globals().items())
             if k.startswith("test_") and callable(v)]
    passed, failed = 0, 0
    for name, fn in tests:
        try:
            if "tmp_path" in fn.__code__.co_varnames[:fn.__code__.co_argcount]:
                import tempfile
                with tempfile.TemporaryDirectory() as d:
                    fn(Path(d))
            elif fn.__code__.co_argcount > 0:
                continue  # parametrized test, needs pytest
            else:
                fn()
            passed += 1
        except Exception:
            failed += 1
            print(f"FAILED: {name}")
            traceback.print_exc()
    print(f"\n{passed} passed, {failed} failed (parametrized tests skipped without pytest)")
