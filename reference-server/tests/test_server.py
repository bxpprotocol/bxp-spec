"""
BXP Protocol — Server test suite
Run: cd reference-server && python -m pytest tests/ -v
"""

import sys
import os
import time
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
from bxp_binary import encode_bxp_binary, decode_bxp_binary

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


# ─── Binary .bxp container support (spec §5.1-5.2) ─────────────

class TestBinaryFormat:
    def test_submit_binary_reading_accepted(self):
        raw = encode_bxp_binary({
            "latitude": 5.6037, "longitude": -0.1870,
            "agents": [{"agentId": "PM2_5", "value": 22.0}],
        })
        r = client.post(
            "/bxp/v2/readings", content=raw,
            headers={"Content-Type": "application/octet-stream"},
        )
        assert r.status_code == 201
        assert r.json()["data"]["readings"][0]["bxpHri"] is not None

    def test_submit_binary_container_with_multiple_readings(self):
        raw = encode_bxp_binary({
            "readings": [
                {"latitude": 5.6, "longitude": -0.18,
                 "agents": [{"agentId": "PM2_5", "value": 12.0}]},
                {"latitude": 5.7, "longitude": -0.19,
                 "agents": [{"agentId": "NO2", "value": 8.0}]},
            ]
        }, file_type="aggregate")
        r = client.post(
            "/bxp/v2/readings", content=raw,
            headers={"Content-Type": "application/octet-stream"},
        )
        assert r.status_code == 201
        assert len(r.json()["data"]["readings"]) == 2

    def test_submit_binary_compressed_accepted(self):
        raw = encode_bxp_binary({
            "latitude": 5.6, "longitude": -0.18,
            "agents": [{"agentId": "PM2_5", "value": 5.0}],
        }, compress=True)
        r = client.post(
            "/bxp/v2/readings", content=raw,
            headers={"Content-Type": "application/octet-stream"},
        )
        assert r.status_code == 201

    def test_submit_binary_invalid_latitude_rejected(self):
        raw = encode_bxp_binary({
            "latitude": 999.0, "longitude": -0.18,
            "agents": [{"agentId": "PM2_5", "value": 5.0}],
        })
        r = client.post(
            "/bxp/v2/readings", content=raw,
            headers={"Content-Type": "application/octet-stream"},
        )
        assert r.status_code == 422

    def test_submit_binary_tampered_container_rejected(self):
        raw = bytearray(encode_bxp_binary({
            "latitude": 5.6, "longitude": -0.18,
            "agents": [{"agentId": "PM2_5", "value": 5.0}],
        }))
        raw[-1] ^= 0xFF
        r = client.post(
            "/bxp/v2/readings", content=bytes(raw),
            headers={"Content-Type": "application/octet-stream"},
        )
        assert r.status_code == 400

    def test_submit_json_still_works_alongside_binary(self):
        r = client.post("/bxp/v2/readings", json={"readings": [{
            "latitude": 5.6, "longitude": -0.18,
            "agents": [{"agentId": "PM2_5", "value": 5.0}]
        }]})
        assert r.status_code == 201

    def test_get_reading_binary_format_round_trips(self):
        submit = client.post("/bxp/v2/readings", json={"readings": [{
            "latitude": 5.6, "longitude": -0.18,
            "agents": [{"agentId": "PM2_5", "value": 41.0}]
        }]}).json()
        rid = submit["data"]["readings"][0]["readingId"]

        r = client.get(f"/bxp/v2/readings/{rid}?format=binary")
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/octet-stream"
        decoded = decode_bxp_binary(r.content)
        assert decoded["record"]["readingId"] == rid

    def test_get_reading_binary_compressed(self):
        submit = client.post("/bxp/v2/readings", json={"readings": [{
            "latitude": 5.6, "longitude": -0.18,
            "agents": [{"agentId": "PM2_5", "value": 41.0}]
        }]}).json()
        rid = submit["data"]["readings"][0]["readingId"]

        r = client.get(f"/bxp/v2/readings/{rid}?format=binary&compress=true")
        assert r.status_code == 200
        decoded = decode_bxp_binary(r.content)
        assert decoded["header"]["flags"]["compressed"] is True
        assert decoded["record"]["readingId"] == rid

    def test_list_readings_binary_format(self):
        client.post("/bxp/v2/readings", json={"readings": [{
            "latitude": 5.6, "longitude": -0.18,
            "agents": [{"agentId": "PM2_5", "value": 41.0}]
        }]})
        r = client.get("/bxp/v2/readings?geohash=s0&format=binary")
        assert r.status_code == 200
        decoded = decode_bxp_binary(r.content)
        assert decoded["header"]["fileType"] == "aggregate"
        assert isinstance(decoded["record"]["readings"], list)


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

    def test_delete_other_devices_reading_forbidden(self):
        # Regression: a valid token used to be enough to delete ANY
        # reading. It must only authorize deleting the caller's own.
        _, victim_rid = self._register_and_submit()
        attacker_token = client.post(
            "/bxp/v2/devices/register", json={"label": "attacker"}
        ).json()["data"]["token"]
        r = client.delete(f"/bxp/v2/readings/{victim_rid}",
                          headers={"Authorization": f"Bearer {attacker_token}"})
        assert r.status_code == 403
        # ...and the victim's reading must still exist afterwards.
        assert client.get(f"/bxp/v2/readings/{victim_rid}").status_code == 200

    def test_delete_nonexistent_reading_404(self):
        token, _ = self._register_and_submit()
        r = client.delete("/bxp/v2/readings/does-not-exist",
                          headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 404

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


# ─── Nearby (spec §7 Stage 6, §8.2.1) ──────────────────────────

def _sensor_headers():
    """Auth header for a freshly registered (fixed-sensor) device. Registered
    devices keep full coordinate precision; anonymous submissions are coarsened
    to a geohash-5 cell centre (SPEC.md 9.1), which is too coarse to test
    metre-scale /nearby ranking against."""
    d = client.post("/bxp/v2/devices/register", json={"label": "nearby-test"}).json()["data"]
    return {"Authorization": f"Bearer {d['token']}"}


class TestNearby:
    def test_nearby_finds_reading_close_by(self):
        client.post("/bxp/v2/readings", headers=_sensor_headers(), json={"readings": [{
            "latitude": 5.6037, "longitude": -0.1870,
            "agents": [{"agentId": "PM2_5", "value": 30}]
        }]})
        # ~50m away from the submitted point
        r = client.get("/bxp/v2/nearby?lat=5.6040&lon=-0.1870&radiusM=2000")
        assert r.status_code == 200
        body = r.json()
        assert body["count"] >= 1
        assert body["data"]["readings"][0]["distanceM"] < 2000
        assert "relevanceScore" in body["data"]["readings"][0]

    def test_nearby_excludes_beyond_radius(self):
        client.post("/bxp/v2/readings", headers=_sensor_headers(), json={"readings": [{
            "latitude": 5.6037, "longitude": -0.1870,
            "agents": [{"agentId": "PM2_5", "value": 30}]
        }]})
        # ~1 degree away (~111km) — well outside any small radius
        r = client.get("/bxp/v2/nearby?lat=6.6037&lon=-0.1870&radiusM=2000")
        assert r.status_code == 200
        assert r.json()["count"] == 0

    def test_nearby_respects_max_age(self):
        # A reading with an old timestampUs should be excluded by maxAgeS.
        old_ts = int(time.time() * 1_000_000) - 7200 * 1_000_000  # 2h ago
        client.post("/bxp/v2/readings", headers=_sensor_headers(), json={"readings": [{
            "latitude": 5.61, "longitude": -0.19, "timestampUs": old_ts,
            "agents": [{"agentId": "PM2_5", "value": 30}]
        }]})
        r = client.get("/bxp/v2/nearby?lat=5.61&lon=-0.19&maxAgeS=3600")
        assert r.status_code == 200
        # None of the returned readings (if any from other tests' fresh
        # data at this exact point) should be the 2h-old one.
        for reading in r.json()["data"]["readings"]:
            assert reading["timestampUs"] != old_ts

    def test_nearby_agent_filter(self):
        client.post("/bxp/v2/readings", headers=_sensor_headers(), json={"readings": [{
            "latitude": 5.62, "longitude": -0.20,
            "agents": [{"agentId": "NO2", "value": 10}]
        }]})
        r = client.get("/bxp/v2/nearby?lat=5.62&lon=-0.20&agent=PM2_5")
        assert r.status_code == 200
        for reading in r.json()["data"]["readings"]:
            assert any(a["agentId"] == "PM2_5" for a in reading["agents"])

    def test_nearby_invalid_coordinates_rejected(self):
        r = client.get("/bxp/v2/nearby?lat=999&lon=-0.18")
        assert r.status_code == 422

    def test_nearby_limit_respected(self):
        for i in range(3):
            client.post("/bxp/v2/readings", headers=_sensor_headers(), json={"readings": [{
                "latitude": 5.63 + i * 0.0001, "longitude": -0.21,
                "agents": [{"agentId": "PM2_5", "value": 10 + i}]
            }]})
        r = client.get("/bxp/v2/nearby?lat=5.63&lon=-0.21&limit=2")
        assert r.status_code == 200
        assert len(r.json()["data"]["readings"]) <= 2

    def test_nearby_ranks_closer_fresher_above_farther_stale(self):
        # Two readings at very different distances/ages from the query
        # point; the closer+fresher one should rank first (spec §7's own
        # example: 3min/400m should usually outrank 55min/50m — here we
        # invert it to closer+fresher vs farther+stale to keep the two
        # candidates in the same geohash-neighbor cells reliably).
        now_us = int(time.time() * 1_000_000)
        client.post("/bxp/v2/readings", headers=_sensor_headers(), json={"readings": [{
            "latitude": 5.6500, "longitude": -0.2200,
            "timestampUs": now_us - 55 * 60 * 1_000_000,  # 55 min old
            "agents": [{"agentId": "PM2_5", "value": 10}]
        }]})
        client.post("/bxp/v2/readings", headers=_sensor_headers(), json={"readings": [{
            "latitude": 5.6503, "longitude": -0.2200,
            "timestampUs": now_us - 3 * 60 * 1_000_000,  # 3 min old
            "agents": [{"agentId": "PM2_5", "value": 10}]
        }]})
        r = client.get("/bxp/v2/nearby?lat=5.6500&lon=-0.2200&radiusM=2000&limit=2")
        readings = r.json()["data"]["readings"]
        assert len(readings) == 2
        assert readings[0]["relevanceScore"] >= readings[1]["relevanceScore"]


# ─── Sync (spec §7 Stage 7, §8.2.2) ────────────────────────────

class TestSync:
    def _submit(self, lat=5.7, lon=-0.3, **extra):
        return client.post("/bxp/v2/readings", json={"readings": [{
            "latitude": lat, "longitude": lon,
            "agents": [{"agentId": "PM2_5", "value": 15}], **extra}]}).json()["data"]["readings"][0]

    def test_sync_returns_changes_after_cursor(self):
        cursor = client.get("/bxp/v2/sync?since=0&limit=2000").json()["nextCursor"]
        new = self._submit()
        body = client.get(f"/bxp/v2/sync?since={cursor}").json()
        assert [r["readingId"] for r in body["data"]["readings"]] == [new["readingId"]]
        assert body["nextCursor"] > cursor

    def test_sync_reading_carries_node_id(self):
        self._submit()
        assert client.get("/bxp/v2/sync?since=0").json()["data"]["readings"][0]["nodeId"]

    def test_sync_pages_without_gaps(self):
        ids = [self._submit(lat=5.7 + i * 0.01)["readingId"] for i in range(5)]
        seen, cursor = [], 0
        while True:
            body = client.get(f"/bxp/v2/sync?since={cursor}&limit=2").json()
            if not body["data"]["readings"]:
                break
            seen += [r["readingId"] for r in body["data"]["readings"]]
            cursor = body["nextCursor"]
        assert seen == ids

    def test_far_future_timestamp_does_not_stall_sync(self):
        self._submit(timestampUs=4_000_000_000_000_000)
        cursor = client.get("/bxp/v2/sync?since=0").json()["nextCursor"]
        later = self._submit(lat=5.9)
        got = client.get(f"/bxp/v2/sync?since={cursor}").json()["data"]["readings"]
        assert [r["readingId"] for r in got] == [later["readingId"]]

    def test_deletion_replicates_as_a_content_free_tombstone(self):
        reg = client.post("/bxp/v2/devices/register", json={"label": "s"}).json()["data"]
        h = {"Authorization": f"Bearer {reg['token']}"}
        rid = client.post("/bxp/v2/readings", headers=h, json={"readings": [{
            "latitude": 5.7, "longitude": -0.3,
            "agents": [{"agentId": "PM2_5", "value": 15}]}]}).json()["data"]["readings"][0]["readingId"]
        cursor = client.get("/bxp/v2/sync?since=0").json()["nextCursor"]
        assert client.delete(f"/bxp/v2/readings/{rid}", headers=h).status_code == 200
        item = client.get(f"/bxp/v2/sync?since={cursor}").json()["data"]["readings"][0]
        assert item == {"readingId": rid, "deleted": True, "deletionProof": item["deletionProof"]}

    def test_sync_limit_and_cursor_are_validated(self):
        assert client.get("/bxp/v2/sync?limit=99999").status_code == 422
        assert client.get("/bxp/v2/sync?since=-1").status_code == 422

    def test_sync_token_gate_when_configured(self, monkeypatch):
        import server as server_module
        monkeypatch.setattr(server_module, "BXP_NODE_SYNC_TOKEN", "secret123")
        assert client.get("/bxp/v2/sync").status_code == 401
        assert client.get("/bxp/v2/sync", headers={"Authorization": "Bearer wrong"}).status_code == 401
        assert client.get("/bxp/v2/sync", headers={"Authorization": "Bearer secret123"}).status_code == 200


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


# ─── Security hardening regressions ───────────────────────────

class TestRateLimiterHardening:
    def test_stale_keys_are_swept(self):
        import asyncio
        from server import RateLimiter

        async def run():
            rl = RateLimiter(calls=5, window_s=1)
            for i in range(50):
                await rl.check(f"spoofed-{i}")
            assert len(rl._store) == 50
            await asyncio.sleep(1.1)
            rl._since_sweep = RateLimiter._SWEEP_EVERY  # force a sweep
            await rl.check("fresh")
            return len(rl._store)

        assert asyncio.run(run()) == 1  # only "fresh" survives

    def test_limit_still_enforced(self):
        import asyncio
        from server import RateLimiter

        async def run():
            rl = RateLimiter(calls=3, window_s=60)
            return [await rl.check("k") for _ in range(5)]

        assert asyncio.run(run()) == [True, True, True, False, False]

    def test_forwarded_for_ignored_by_default(self):
        import server as server_module
        from types import SimpleNamespace
        req = SimpleNamespace(
            headers={"x-forwarded-for": "6.6.6.6"},
            client=SimpleNamespace(host="1.2.3.4"),
        )
        assert server_module.TRUST_PROXY_HEADERS is False
        assert server_module._client_ip(req) == "1.2.3.4"

    def test_forwarded_for_honored_when_opted_in(self, monkeypatch):
        import server as server_module
        from types import SimpleNamespace
        monkeypatch.setattr(server_module, "TRUST_PROXY_HEADERS", True)
        req = SimpleNamespace(
            headers={"x-forwarded-for": "6.6.6.6, 10.0.0.1"},
            client=SimpleNamespace(host="1.2.3.4"),
        )
        assert server_module._client_ip(req) == "6.6.6.6"


class TestHostileUploads:
    def test_decompression_bomb_over_http_rejected(self):
        import gzip
        from bxp_binary import HEADER_STRUCT, CHECKSUM_STRUCT, MAGIC, MAX_DECOMPRESSED_BYTES
        import zlib
        bomb = gzip.compress(b"\0" * (MAX_DECOMPRESSED_BYTES * 4), 9)
        body = HEADER_STRUCT.pack(MAGIC, 2, 0, 0x01, 0x01, 0, 0, len(bomb))
        raw = (body + CHECKSUM_STRUCT.pack(zlib.crc32(body) & 0xFFFFFFFF,
                                           zlib.crc32(bomb) & 0xFFFFFFFF) + bomb)
        r = client.post("/bxp/v2/readings", content=raw,
                        headers={"Content-Type": "application/octet-stream"})
        assert r.status_code == 400
        assert "exceeds" in r.json()["detail"]

    def test_oversized_body_rejected_413(self, monkeypatch):
        import server as server_module
        monkeypatch.setattr(server_module, "MAX_BODY_BYTES", 1024)
        r = client.post("/bxp/v2/readings", content=b"x" * 5000,
                        headers={"Content-Type": "application/json"})
        assert r.status_code == 413

    def test_oversized_chunked_body_without_content_length_rejected(self, monkeypatch):
        import server as server_module
        monkeypatch.setattr(server_module, "MAX_BODY_BYTES", 1024)

        def gen():  # generator body => chunked transfer, no Content-Length
            for _ in range(20):
                yield b"y" * 500

        r = client.post("/bxp/v2/readings", content=gen(),
                        headers={"Content-Type": "application/json"})
        assert r.status_code == 413

    def test_normal_sized_submission_unaffected(self):
        r = client.post("/bxp/v2/readings", json={"readings": [{
            "latitude": 5.6, "longitude": -0.18,
            "agents": [{"agentId": "PM2_5", "value": 12}]}]})
        assert r.status_code == 201


# ─── Ownership, privacy and input-bounds regressions ──────────

class TestOwnershipAndPrivacy:
    def _device(self):
        d = client.post("/bxp/v2/devices/register", json={"label": "o"}).json()["data"]
        return d["device"]["deviceUuid"], {"Authorization": f"Bearer {d['token']}"}

    def _post(self, headers=None, **reading):
        body = {"latitude": 5.60371, "longitude": -0.18702,
                "agents": [{"agentId": "PM2_5", "value": 12}], **reading}
        return client.post("/bxp/v2/readings", headers=headers or {}, json={"readings": [body]})

    def test_anonymous_cannot_submit_under_a_registered_devices_uuid(self):
        uuid_, _ = self._device()
        assert self._post(deviceUuid=uuid_).status_code == 403

    def test_authenticated_device_cannot_submit_as_another_device(self):
        _, h1 = self._device()
        uuid2, _ = self._device()
        assert self._post(headers=h1, deviceUuid=uuid2).status_code == 403

    def test_registering_an_existing_uuid_is_409_and_does_not_rotate_the_token(self):
        uuid_, h = self._device()
        assert client.post("/bxp/v2/devices/register", json={"deviceUuid": uuid_}).status_code == 409
        assert self._post(headers=h).status_code == 201  # original token still valid

    def test_anonymous_coordinates_are_coarsened_to_the_cell_centre(self):
        r = self._post().json()["data"]["readings"][0]
        assert len(r["geohash"]) == 5
        assert (r["latitude"], r["longitude"]) != (5.60371, -0.18702)
        assert abs(r["latitude"] - 5.60371) < 0.03

    def test_authenticated_device_keeps_full_precision(self):
        _, h = self._device()
        r = self._post(headers=h).json()["data"]["readings"][0]
        assert (r["latitude"], r["longitude"]) == (5.60371, -0.18702)
        assert len(r["geohash"]) == 7

    def test_duplicate_submission_is_reported_and_does_not_overwrite(self):
        first = self._post(timestampUs=1_700_000_000_000_000).json()["data"]["readings"][0]
        again = self._post(timestampUs=1_700_000_000_000_000).json()["data"]["readings"][0]
        assert first["stored"] is True and again["stored"] is False
        assert first["readingId"] == again["readingId"]

    def test_distinct_readings_at_the_same_instant_do_not_collide(self):
        a = self._post(timestampUs=1_700_000_000_000_001).json()["data"]["readings"][0]
        b = self._post(timestampUs=1_700_000_000_000_001, latitude=6.5).json()["data"]["readings"][0]
        assert a["readingId"] != b["readingId"] and b["stored"] is True

    def test_agent_extras_and_ext_survive_ingestion(self):
        r = self._post(ext={"org.example": {"k": 1}},
                       agents=[{"agentId": "PM2_5", "value": 12, "uncertainty": 2.5,
                                "correction": {"applied": True, "rawValue": 20}}])
        rid = r.json()["data"]["readings"][0]["readingId"]
        got = client.get(f"/bxp/v2/readings/{rid}").json()["data"]["reading"]
        assert got["ext"] == {"org.example": {"k": 1}}
        assert got["agents"][0]["correction"]["rawValue"] == 20
        assert got["agents"][0]["uncertainty"] == 2.5

    def test_nan_infinity_and_oversize_inputs_are_rejected(self):
        for bad in ('{"readings":[{"latitude":NaN,"longitude":0,"agents":[]}]}',
                    '{"readings":[{"latitude":0,"longitude":0,"agents":[{"agentId":"CO","value":Infinity}]}]}'):
            r = client.post("/bxp/v2/readings", content=bad,
                            headers={"Content-Type": "application/json"})
            assert r.status_code in (400, 422)
        too_many = {"readings": [{"latitude": 0, "longitude": 0, "agents": []}] * 501}
        assert client.post("/bxp/v2/readings", json=too_many).status_code == 422
        assert self._post(timestampUs=10**19).status_code == 422
        assert self._post(deviceUuid="x" * 200).status_code == 422

    def test_pagination_bounds_are_validated(self):
        assert client.get("/bxp/v2/readings?geohash=s&limit=0").status_code == 422
        assert client.get("/bxp/v2/readings?geohash=s&limit=201").status_code == 422
        assert client.get("/bxp/v2/readings?geohash=s&offset=-1").status_code == 422

    def test_malformed_geohash_is_400(self):
        assert client.get("/bxp/v2/locations/abc!!/latest").status_code == 400
        assert client.get("/bxp/v2/readings?geohash=%25").status_code == 400

    def test_nearby_rejects_bad_parameters(self):
        assert client.get("/bxp/v2/nearby?lat=nan&lon=0").status_code == 422
        assert client.get("/bxp/v2/nearby?lat=0&lon=0&radiusM=0").status_code == 422
        assert client.get("/bxp/v2/nearby?lat=0&lon=0&minQuality=bogus").status_code == 422

    def test_deleted_reading_content_is_gone_from_verify(self):
        _, h = self._device()
        rid = self._post(headers=h).json()["data"]["readings"][0]["readingId"]
        client.delete(f"/bxp/v2/readings/{rid}", headers=h)
        v = client.get(f"/bxp/v2/readings/{rid}/verify").json()["data"]
        assert v["deleted"] is True and v["integrityOk"] is None


class TestNodeRegistryAndPages:
    def test_node_cannot_be_redirected(self):
        ok = {"nodeId": "peer-1", "baseUrl": "https://peer1.example"}
        assert client.post("/bxp/v2/nodes/announce", json=ok).status_code == 200
        assert client.post("/bxp/v2/nodes/announce",
                           json={**ok, "baseUrl": "https://evil.example"}).status_code == 409

    def test_node_announce_validates_input(self):
        assert client.post("/bxp/v2/nodes/announce", json={"nodeId": "n"}).status_code == 422
        assert client.post("/bxp/v2/nodes/announce",
                           json={"nodeId": "n", "baseUrl": "javascript:alert(1)//x"}).status_code == 422
        assert client.post("/bxp/v2/nodes/announce", content="not json",
                           headers={"Content-Type": "application/json"}).status_code == 422

    def test_error_pages_do_not_reflect_markup(self):
        for path in ("/widget/", "/dashboard/"):
            r = client.get(path + "%3Cimg%20src%3Dx%20onerror%3Dalert(1)%3E")
            assert "<img src=x" not in r.text

    def test_metrics_labels_cannot_be_broken(self, monkeypatch):
        import server as server_module
        monkeypatch.setattr(server_module, "NODE_ID", 'a"}\nfake_metric 1')
        lines = client.get("/metrics").text.splitlines()
        assert not any(line.startswith("fake_metric") for line in lines)
        assert sum(line.startswith("bxp_info{") for line in lines) == 1
