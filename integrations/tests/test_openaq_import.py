"""
Tests for integrations/openaq_import.py, run entirely against the offline
fixture in fixtures/openaq_sample_locations.json -- no network required.

This checks the conversion logic (OpenAQ JSON -> BXP record) end-to-end,
including the specific trust distinction that's the whole point of this
importer: a reference monitor (isMonitor: true) must come out VALIDATED
with an explicit qcMethod, and a low-cost sensor (isMonitor: false) must
come out UNVALIDATED -- never the reverse, and never VALIDATED without
justification (SPEC.md §5.5.1, enforced by validate_bxp_record()).

Run with:
    cd integrations && python3 tests/test_openaq_import.py
or via the sandbox pytest-shim runner used elsewhere in this repo.
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent.parent / "sdk" / "python"))

try:
    import pytest  # noqa: F401  (optional; only needed if run under real pytest)
except ImportError:
    pytest = None

from openaq_import import import_from_fixture, openaq_location_to_bxp_records
from bxp_sdk import validate_bxp_record

FIXTURE = HERE.parent / "fixtures" / "openaq_sample_locations.json"


def _load_fixture_data():
    return json.loads(FIXTURE.read_text())


def test_fixture_produces_one_record_per_location():
    records = import_from_fixture(str(FIXTURE))
    assert len(records) == 2


def test_reference_monitor_is_validated_with_explicit_qc_method():
    records = import_from_fixture(str(FIXTURE))
    ref = next(r for r in records if r["context"]["openaqProvider"] == "AirNow")
    assert ref["quality"]["flag"] == "VALIDATED"
    assert "openaq-reference-monitor" in ref["quality"]["qcMethod"]


def test_low_cost_sensor_is_unvalidated():
    records = import_from_fixture(str(FIXTURE))
    lowcost = next(r for r in records if r["context"]["openaqProvider"] == "AfriqAir Low-Cost Network")
    assert lowcost["quality"]["flag"] == "UNVALIDATED"


def test_every_converted_record_is_bxp_valid():
    records = import_from_fixture(str(FIXTURE))
    for r in records:
        result = validate_bxp_record(r)
        assert result["valid"], f"invalid record: {result['errors']}"
        # Reference-monitor VALIDATED records must not trip the
        # justification warning (they have an explicit qcMethod);
        # low-cost UNVALIDATED records never trigger that check at all.
        assert not any("VALIDATED but no agent" in w for w in result["warnings"])


def test_device_uuid_is_a_real_uuid_and_deterministic():
    records1 = import_from_fixture(str(FIXTURE))
    records2 = import_from_fixture(str(FIXTURE))
    import uuid as uuid_mod
    for r in records1:
        uuid_mod.UUID(r["deviceUuid"])  # raises ValueError if not a real UUID
    ids1 = sorted(r["deviceUuid"] for r in records1)
    ids2 = sorted(r["deviceUuid"] for r in records2)
    assert ids1 == ids2  # same OpenAQ location -> same deviceUuid every time


def test_multiple_agents_at_same_timestamp_share_one_record():
    records = import_from_fixture(str(FIXTURE))
    ref = next(r for r in records if r["context"]["openaqProvider"] == "AirNow")
    agent_ids = {a["agentId"] for a in ref["agents"]}
    assert agent_ids == {"PM2_5", "TEMP"}


def test_unmapped_parameter_is_silently_skipped_not_fatal():
    data = _load_fixture_data()
    location = dict(data["locations"][0])
    location["sensors"] = list(location["sensors"]) + [{
        "id": 999999, "name": "particle count",
        "parameter": {"id": 999, "name": "um003", "units": "particles/cm3", "displayName": "PC0.3"},
    }]
    latest = list(data["latest_by_location"]["8118"]) + [{
        "datetime": {"utc": "2026-09-20T12:00:00Z"}, "value": 123.0,
        "sensorsId": 999999, "locationsId": location["id"],
    }]
    records = openaq_location_to_bxp_records(location, latest)
    for r in records:
        assert all(a["agentId"] != "um003" for a in r["agents"])


def test_no_network_calls_in_fixture_path(monkeypatch):
    # Belt-and-suspenders: assert the offline path never touches urllib.
    import openaq_import as mod

    def _boom(*a, **kw):
        raise AssertionError("fixture path must not hit the network")

    monkeypatch.setattr(mod.urllib.request, "urlopen", _boom)
    records = import_from_fixture(str(FIXTURE))
    assert len(records) == 2


if __name__ == "__main__":
    # Minimal standalone runner for environments without pytest.
    import traceback
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    passed = failed = 0
    for t in tests:
        try:
            if "monkeypatch" in t.__code__.co_varnames[:t.__code__.co_argcount]:
                class _MP:
                    def setattr(self, obj, name, value):
                        setattr(obj, name, value)
                t(_MP())
            else:
                t()
            print(f"  PASS  {t.__name__}")
            passed += 1
        except Exception as e:
            print(f"  FAIL  {t.__name__}: {e}")
            traceback.print_exc()
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
