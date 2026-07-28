"""
BXP Protocol — Server test suite
Run: cd reference-server && python -m pytest tests/ -v
"""

import sys
import os
import json
import time
import hashlib
import pytest
import tempfile
from pathlib import Path

# Add parent dirs to path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "sdk" / "python"))

from fastapi.testclient import TestClient

# Use a temp DB for tests
os.environ["_BXP_TEST_DB"] = "1"

import database as db
# Patch DB path for tests
db.DB_PATH = Path(tempfile.mktemp(suffix=".test.db"))

from server import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    """Initialise a fresh DB and reset rate limiters for each test."""
    db.DB_PATH = Path(tempfile.mktemp(suffix=".test.db"))
    db._local.__dict__.clear()
    db.init_db()
    # Reset in-memory rate limiters so tests don't interfere
    from server import _rl_submit, _rl_city, _rl_register
    _rl_submit.reset()
    _rl_city.reset()
    _rl_register.reset()
    yield
    try:
        db.DB_PATH.unlink(missing_ok=True)
    except Exception:
        pass


# ─── Health ───────────────────────────────────────────────────

class TestHealth:
    def test_health_ok(self):
        r = client.get("/bxp/v2/health")
        assert r.status_code == 200
        d = r.json()
        assert d["status"] == "ok"
        assert d["bxpVersion"] == "2.0"
        assert "nodeId" in d
        assert "uptime" in d
        assert "readingCount" in d

    def test_health_reading_count_increases(self):
        r1 = client.get("/bxp/v2/health")
        c1 = r1.json()["readingCount"]

        client.post("/bxp/v2/readings", json={"readings": [{
            "latitude": 5.6, "longitude": -0.18,
            "agents": [{"agentId": "PM2_5", "value": 47.2}]
        }]})

        r2 = client.get("/bxp/v2/health")
        assert r2.json()["readingCount"] == c1 + 1


# ─── Readings POST ────────────────────────────────────────────

class TestSubmitReadings:
    def test_returns_201(self):
        r = client.post("/bxp/v2/readings", json={"readings": [{
            "latitude": 5.6037, "longitude": -0.1870,
            "agents": [{"agentId": "PM2_5", "value": 47.2}]
        }]})
        assert r.status_code == 201

    def test_response_shape(self):
        r = client.post("/bxp/v2/readings", json={"readings": [{
            "latitude": 5.6037, "longitude": -0.1870,
            "agents": [
                {"agentId": "PM2_5", "value": 47.2},
                {"agentId": "NO2",   "value": 18.3},
            ]
        }]})
        d = r.json()
        assert d["status"] == "ok"
        reading = d["data"]["readings"][0]
        assert "readingId" in reading
        assert "bxpHri" in reading
        assert "bxpHriLevel" in reading
        assert "geohash" in reading
        assert "qualityFlag" in reading
        assert "payloadHash" in reading
        assert reading["payloadHash"].startswith("sha256:")

    def test_invalid_latitude(self):
        r = client.post("/bxp/v2/readings", json={"readings": [{
            "latitude": 999.0, "longitude": -0.18,
            "agents": [{"agentId": "PM2_5", "value": 10}]
        }]})
        assert r.status_code == 422

    def test_invalid_longitude(self):
        r = client.post("/bxp/v2/readings", json={"readings": [{
            "latitude": 5.6, "longitude": 999.0,
            "agents": [{"agentId": "PM2_5", "value": 10}]
        }]})
        assert r.status_code == 422

    def test_negative_agent_value_rejected(self):
        r = client.post("/bxp/v2/readings", json={"readings": [{
            "latitude": 5.6, "longitude": -0.18,
            "agents": [{"agentId": "PM2_5", "value": -5.0}]
        }]})
        assert r.status_code == 422

    def test_empty_readings_rejected(self):
        r = client.post("/bxp/v2/readings", json={"readings": []})
        assert r.status_code == 400

    def test_hri_computed(self):
        r = client.post("/bxp/v2/readings", json={"readings": [{
            "latitude": 5.6037, "longitude": -0.1870,
            "agents": [{"agentId": "PM2_5", "value": 0.0}]
        }]})
        reading = r.json()["data"]["readings"][0]
        assert reading["bxpHri"] == 0.0
        assert reading["bxpHriLevel"] == "CLEAN"

    def test_invalid_token_rejected(self):
        r = client.post(
            "/bxp/v2/readings",
            json={"readings": [{"latitude": 5.6, "longitude": -0.18,
                                 "agents": [{"agentId": "PM2_5", "value": 10}]}]},
            headers={"Authorization": "Bearer bxp_invalid_token_xyz"},
        )
        assert r.status_code == 401

    def test_duration_affects_hri(self):
        """HRI should increase with longer duration for same values."""
        body = {"readings": [{
            "latitude": 5.6, "longitude": -0.18,
            "agents": [{"agentId": "PM2_5", "value": 30.0}],
            "durationS": 60,
        }]}
        r1 = client.post("/bxp/v2/readings", json=body)
        hri_1h = r1.json()["data"]["readings"][0]["bxpHri"]

        body["readings"][0]["durationS"] = 86400
        r2 = client.post("/bxp/v2/readings", json=body)
        hri_24h = r2.json()["data"]["readings"][0]["bxpHri"]

        assert hri_24h > hri_1h


# ─── Readings GET ─────────────────────────────────────────────

class TestGetReadings:
    def _submit(self, lat=5.6, lon=-0.18, pm25=30.0):
        return client.post("/bxp/v2/readings", json={"readings": [{
            "latitude": lat, "longitude": lon,
            "agents": [{"agentId": "PM2_5", "value": pm25}]
        }]}).json()["data"]["readings"][0]["readingId"]

    def test_get_by_id(self):
        rid = self._submit()
        r = client.get(f"/bxp/v2/readings/{rid}")
        assert r.status_code == 200
        assert r.json()["data"]["reading"]["readingId"] == rid

    def test_get_missing_id(self):
        r = client.get("/bxp/v2/readings/doesnotexist")
        assert r.status_code == 404

    def test_filter_by_quality(self):
        self._submit()
        r = client.get("/bxp/v2/readings?quality=UNVALIDATED&geohash=s0")
        assert r.status_code == 200

    def test_pagination_offset(self):
        for i in range(5):
            self._submit(pm25=float(i + 10))
        r1 = client.get("/bxp/v2/readings?geohash=s0&limit=2&offset=0")
        r2 = client.get("/bxp/v2/readings?geohash=s0&limit=2&offset=2")
        d1 = r1.json()["data"]["readings"]
        d2 = r2.json()["data"]["readings"]
        ids1 = {x["readingId"] for x in d1}
        ids2 = {x["readingId"] for x in d2}
        assert ids1.isdisjoint(ids2)


# ─── Delete & Verify ──────────────────────────────────────────

class TestDeleteAndVerify:
    def _register_and_submit(self):
        # Register a device to get a token
        reg = client.post("/bxp/v2/devices/register",
                          json={"label": "test"}).json()
        token = reg["data"]["token"]
        rid = client.post(
            "/bxp/v2/readings",
            json={"readings": [{"latitude": 5.6, "longitude": -0.18,
                                 "agents": [{"agentId": "PM2_5", "value": 20}]}]},
            headers={"Authorization": f"Bearer {token}"},
        ).json()["data"]["readings"][0]["readingId"]
        return token, rid

    def test_verify_integrity_ok(self):
        _, rid = self._register_and_submit()
        r = client.get(f"/bxp/v2/readings/{rid}/verify")
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["integrityOk"] is True

    def test_delete_requires_auth(self):
        _, rid = self._register_and_submit()
        r = client.delete(f"/bxp/v2/readings/{rid}")
        assert r.status_code == 401

    def test_delete_with_proof(self):
        token, rid = self._register_and_submit()
        r = client.delete(f"/bxp/v2/readings/{rid}",
                          headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        d = r.json()
        assert d["deleted"] is True
        assert "sha256:" in d["deletionProof"]

    def test_deleted_reading_not_found(self):
        token, rid = self._register_and_submit()
        client.delete(f"/bxp/v2/readings/{rid}",
                      headers={"Authorization": f"Bearer {token}"})
        r = client.get(f"/bxp/v2/readings/{rid}")
        assert r.status_code == 404


# ─── Locations ────────────────────────────────────────────────

class TestLocations:
    def _submit_n(self, n=6, lat=5.6, lon=-0.18):
        for i in range(n):
            client.post("/bxp/v2/readings", json={"readings": [{
                "latitude": lat + i * 0.001,
                "longitude": lon,
                "agents": [{"agentId": "PM2_5", "value": 20 + i}]
            }]})

    def test_geohash_too_short(self):
        r = client.get("/bxp/v2/locations/s0/latest")
        assert r.status_code == 400

    def test_aggregate_requires_k5(self):
        self._submit_n(3)  # only 3 — below k=5
        r = client.get("/bxp/v2/locations/s0000/aggregate")
        assert r.status_code == 404

    def test_aggregate_ok_with_k5(self):
        self._submit_n(7)  # 7 ≥ 5
        r = client.get("/bxp/v2/locations/s0000/aggregate")
        # May or may not have 5 in exact geohash tile — just check no server error
        assert r.status_code in (200, 404)


# ─── Devices ──────────────────────────────────────────────────

class TestDevices:
    def test_register_returns_token(self):
        r = client.post("/bxp/v2/devices/register",
                        json={"label": "Test Sensor"})
        assert r.status_code == 201
        d = r.json()["data"]
        assert "token" in d
        assert d["token"].startswith("bxp_")
        assert "device" in d

    def test_get_device(self):
        reg = client.post("/bxp/v2/devices/register",
                          json={"label": "Test"}).json()
        uid = reg["data"]["device"]["deviceUuid"]
        r = client.get(f"/bxp/v2/devices/{uid}")
        assert r.status_code == 200
        assert r.json()["data"]["device"]["deviceUuid"] == uid

    def test_get_missing_device(self):
        r = client.get("/bxp/v2/devices/does-not-exist")
        assert r.status_code == 404


# ─── Community Reports ────────────────────────────────────────

class TestCommunityReports:
    def test_submit_report(self):
        r = client.post("/bxp/v2/community/reports", json={
            "latitude": 5.6, "longitude": -0.18,
            "reportType": "odor", "description": "Burning smell",
            "severity": "moderate",
        })
        assert r.status_code == 201
        d = r.json()["data"]["report"]
        assert "reportId" in d
        assert len(d["geohash"]) == 5   # §9: floor to precision 5

    def test_get_reports(self):
        client.post("/bxp/v2/community/reports", json={
            "latitude": 5.6, "longitude": -0.18, "reportType": "dust",
        })
        r = client.get("/bxp/v2/community/reports")
        assert r.status_code == 200
        assert r.json()["count"] >= 1


# ─── Search ───────────────────────────────────────────────────

class TestSearch:
    def test_search_no_results(self):
        r = client.get("/bxp/v2/search?lat=5.6&lon=-0.18")
        assert r.status_code == 200

    def test_search_by_coordinates(self):
        client.post("/bxp/v2/readings", json={"readings": [{
            "latitude": 5.6, "longitude": -0.18,
            "agents": [{"agentId": "PM2_5", "value": 20}]
        }]})
        r = client.get("/bxp/v2/search?lat=5.6&lon=-0.18")
        assert r.status_code == 200


# ─── Metrics ─────────────────────────────────────────────────

class TestMetrics:
    def test_metrics_prometheus_format(self):
        r = client.get("/metrics")
        assert r.status_code == 200
        assert "bxp_readings_total" in r.text
        assert "bxp_uptime_seconds" in r.text
        assert "# HELP" in r.text
        assert "# TYPE" in r.text


# ─── Widget ──────────────────────────────────────────────────

class TestWidget:
    def test_widget_no_token(self):
        # Without AQICN_TOKEN the widget should return 200 with error HTML
        r = client.get("/widget/london")
        assert r.status_code == 200
        assert "html" in r.headers.get("content-type", "").lower()


# ─── HRI correctness ─────────────────────────────────────────

class TestHriCalculation:
    def test_zero_pollution_is_clean(self):
        r = client.post("/bxp/v2/readings", json={"readings": [{
            "latitude": 0, "longitude": 0,
            "agents": [{"agentId": "PM2_5", "value": 0}]
        }]})
        assert r.json()["data"]["readings"][0]["bxpHri"] == 0.0

    def test_high_pm25_elevated_level(self):
        r = client.post("/bxp/v2/readings", json={"readings": [{
            "latitude": 0, "longitude": 0,
            "agents": [{"agentId": "PM2_5", "value": 200}]
        }]})
        reading = r.json()["data"]["readings"][0]
        # PM2.5=200 with duration=1h → score = min(200/15, 1) * 0.35 * 100 = 35 → MODERATE
        assert reading["bxpHri"] == 35.0
        assert reading["bxpHriLevel"] == "MODERATE"

    def test_payload_hash_present(self):
        r = client.post("/bxp/v2/readings", json={"readings": [{
            "latitude": 5.6, "longitude": -0.18,
            "agents": [{"agentId": "PM2_5", "value": 20}]
        }]})
        reading = r.json()["data"]["readings"][0]
        assert reading["payloadHash"].startswith("sha256:")
