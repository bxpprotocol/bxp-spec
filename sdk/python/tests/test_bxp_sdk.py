"""
Unit tests for bxp_sdk.py -- the higher-level record builder, reader,
writer, and validator (SPEC.md §5, §5.5.1, §5.8).

This is new: previously only bxp_binary.py had test coverage; the
validate_bxp_record() logic (including the version-compatibility and
calibration/correction trust checks) had none.

Run with (pytest, if installed):
    cd sdk/python && python -m pytest tests/test_bxp_sdk.py -v
or with the sandbox-only zero-dependency runner used to develop this repo:
    PYTHONPATH=. python3 <path-to-shim>/run_tests.py tests/test_bxp_sdk.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from bxp_sdk import (
    write_bxp, read_bxp, validate_bxp_record, encode_geohash,
    calculate_risk, SUPPORTED_MAJOR_VERSION,
)

SAMPLE_DATA = {
    "latitude": 5.5571,
    "longitude": -0.1969,
    "timestampUs": 1710000000000000,
    "agents": [
        {"agentId": "PM2_5", "value": 12.0, "unit": "ug/m3"},
    ],
}


def test_write_then_read_round_trip(tmp_path):
    path = tmp_path / "reading.bxp.json"
    written = write_bxp(str(path), SAMPLE_DATA)
    read_back = read_bxp(str(path))
    assert read_back["_integrityOk"] is True
    assert read_back["deviceUuid"] == written["deviceUuid"]
    assert read_back["agents"][0]["agentId"] == "PM2_5"


def test_geohash_auto_derived_from_lat_lon(tmp_path):
    path = tmp_path / "reading.bxp.json"
    written = write_bxp(str(path), SAMPLE_DATA)
    assert written["geohash"] is not None
    assert len(written["geohash"]) >= 5


def test_geohash_too_low_precision_rejected():
    data = dict(SAMPLE_DATA, geohash="s1v0")  # 4 chars, min is 5
    with pytest.raises(ValueError):
        write_bxp("/tmp/should_not_be_written.bxp.json", data)


def test_missing_agents_rejected():
    data = {"latitude": 5.5, "longitude": -0.2, "timestampUs": 1710000000000000}
    with pytest.raises(ValueError):
        write_bxp("/tmp/should_not_be_written.bxp.json", data)


def test_valid_record_has_no_errors():
    record = write_bxp.__wrapped__ if False else None  # placeholder, unused
    from bxp_sdk import _build_bxp_record
    record = _build_bxp_record(SAMPLE_DATA)
    result = validate_bxp_record(record)
    assert result["valid"] is True
    assert result["errors"] == []


def test_major_version_mismatch_is_an_error():
    from bxp_sdk import _build_bxp_record
    record = _build_bxp_record(SAMPLE_DATA)
    record["bxpVersion"] = "99.0"
    # payloadHash will now mismatch too (expected, separate concern) --
    # recompute so this test isolates the version check specifically.
    import hashlib
    check = {k: v for k, v in record.items() if k != "payloadHash"}
    payload_str = json.dumps(check, sort_keys=True, separators=(",", ":"), default=str)
    record["payloadHash"] = "sha256:" + hashlib.sha256(payload_str.encode()).hexdigest()

    result = validate_bxp_record(record)
    assert result["valid"] is False
    assert any("major version" in e for e in result["errors"])


def test_higher_minor_version_same_major_is_not_flagged():
    # SPEC.md §5.8: a higher minor version than this SDK knows about MUST
    # still be accepted -- it must not even produce a warning, since
    # unrecognized optional fields are simply ignored (§5.7).
    from bxp_sdk import _build_bxp_record
    import hashlib
    record = _build_bxp_record(SAMPLE_DATA)
    record["bxpVersion"] = f"{SUPPORTED_MAJOR_VERSION}.99"
    check = {k: v for k, v in record.items() if k != "payloadHash"}
    payload_str = json.dumps(check, sort_keys=True, separators=(",", ":"), default=str)
    record["payloadHash"] = "sha256:" + hashlib.sha256(payload_str.encode()).hexdigest()

    result = validate_bxp_record(record)
    assert result["valid"] is True
    assert not any("version" in w for w in result["warnings"])


def test_validated_flag_without_justification_warns():
    from bxp_sdk import _build_bxp_record
    import hashlib
    record = _build_bxp_record(SAMPLE_DATA)
    record["quality"] = {"flag": "VALIDATED", "confidence": 0.9,
                          "qcMethod": "bxp-sdk-auto", "notes": None}
    check = {k: v for k, v in record.items() if k != "payloadHash"}
    payload_str = json.dumps(check, sort_keys=True, separators=(",", ":"), default=str)
    record["payloadHash"] = "sha256:" + hashlib.sha256(payload_str.encode()).hexdigest()

    result = validate_bxp_record(record)
    assert result["valid"] is True  # this is a warning, not an error
    assert any("VALIDATED" in w for w in result["warnings"])


def test_validated_flag_with_applied_correction_does_not_warn():
    from bxp_sdk import _build_bxp_record
    import hashlib
    record = _build_bxp_record(SAMPLE_DATA)
    record["agents"][0]["correction"] = {
        "applied": True, "rawValue": 18.0, "model": "epa_pm25_humidity_v1",
    }
    record["quality"] = {"flag": "VALIDATED", "confidence": 0.95,
                          "qcMethod": "bxp-sdk-auto", "notes": None}
    check = {k: v for k, v in record.items() if k != "payloadHash"}
    payload_str = json.dumps(check, sort_keys=True, separators=(",", ":"), default=str)
    record["payloadHash"] = "sha256:" + hashlib.sha256(payload_str.encode()).hexdigest()

    result = validate_bxp_record(record)
    assert not any("VALIDATED" in w for w in result["warnings"])


def test_validated_flag_with_explicit_qc_method_does_not_warn():
    from bxp_sdk import _build_bxp_record
    import hashlib
    record = _build_bxp_record(SAMPLE_DATA)
    record["quality"] = {"flag": "VALIDATED", "confidence": 0.95,
                          "qcMethod": "reference-grade-colocated", "notes": None}
    check = {k: v for k, v in record.items() if k != "payloadHash"}
    payload_str = json.dumps(check, sort_keys=True, separators=(",", ":"), default=str)
    record["payloadHash"] = "sha256:" + hashlib.sha256(payload_str.encode()).hexdigest()

    result = validate_bxp_record(record)
    assert not any("VALIDATED" in w for w in result["warnings"])


def test_tampered_payload_hash_is_an_error(tmp_path):
    path = tmp_path / "reading.bxp.json"
    write_bxp(str(path), SAMPLE_DATA)
    record = json.loads(path.read_text())
    record["agents"][0]["value"] = 999.0  # tamper without updating the hash
    result = validate_bxp_record(record)
    assert result["valid"] is False
    assert any("hash" in e.lower() for e in result["errors"])


def test_negative_agent_value_rejected_at_build_time():
    data = dict(SAMPLE_DATA, agents=[{"agentId": "PM2_5", "value": -1.0, "unit": "ug/m3"}])
    with pytest.raises(ValueError):
        write_bxp("/tmp/should_not_be_written.bxp.json", data)


def test_geohash_is_deterministic():
    a = encode_geohash(5.5571, -0.1969, 7)
    b = encode_geohash(5.5571, -0.1969, 7)
    assert a == b
    assert len(a) == 7


def test_calculate_risk_returns_score_and_level():
    result = calculate_risk(agents=[{"agentId": "PM2_5", "value": 12.0, "unit": "ug/m3"}])
    assert "score" in result and "level" in result
    assert 0 <= result["score"] <= 100
