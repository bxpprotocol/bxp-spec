"""
Tests for database.py and geo.py - the persistence and spatial layers.

These need only the standard library (no FastAPI), so they run anywhere:
    python -m pytest reference-server/tests/test_database.py
Each test starts from a brand-new database file via _fresh().
"""

import sqlite3
import sys
import tempfile
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import database as db  # noqa: E402
import geo  # noqa: E402

NOW_US = int(time.time() * 1_000_000)


def _fresh():
    db.DB_PATH = Path(tempfile.mkdtemp()) / "test.db"
    db.init_db()


def make_record(rid="r1", lat=5.6037, lon=-0.1870, ts=None, device="dev-1",
                quality="UNVALIDATED", agent="PM2_5", hri=10.0, geohash_len=7):
    return {
        "readingId": rid, "bxpVersion": "2.0", "nodeId": "n", "deviceUuid": device,
        "timestamp": "2026-01-01T00:00:00+00:00",
        "timestampUs": ts if ts is not None else NOW_US,
        "latitude": lat, "longitude": lon,
        "geohash": geo.encode_geohash(lat, lon, geohash_len),
        "agents": [{"agentId": agent, "value": 12.0, "unit": "ug/m3"}],
        "readings": {"pm25": 12.0}, "bxpHri": hri, "bxpHriLevel": "CLEAN",
        "quality": {"flag": quality}, "qualityFlag": quality,
        "payloadHash": "sha256:x", "durationS": 60, "indoorOutdoor": "outdoor",
    }


# ─── insert semantics ────────────────────────────────────────

def test_insert_is_idempotent_and_never_overwrites():
    _fresh()
    assert db.insert_reading(make_record("a", hri=10.0)) is True
    tampered = make_record("a", hri=99.0)
    assert db.insert_reading(tampered) is False
    assert db.get_reading("a")["bxpHri"] == 10.0


def test_deleted_reading_cannot_be_resurrected_by_resubmission():
    _fresh()
    db.insert_reading(make_record("a"))
    assert db.delete_reading("a")
    assert db.insert_reading(make_record("a")) is False
    assert db.get_reading("a") is None


def test_batch_insert_is_atomic():
    _fresh()
    good, bad = make_record("g"), make_record("b")
    del bad["readingId"]  # KeyError mid-batch
    with pytest.raises(KeyError):
        db.insert_readings([good, bad])
    assert db.reading_count() == 0


def test_delete_scrubs_content_and_leaves_tombstone():
    _fresh()
    db.insert_reading(make_record("a", lat=5.6037, lon=-0.187))
    proof = db.delete_reading("a")
    assert proof.startswith("sha256:")
    row = sqlite3.connect(db.DB_PATH).execute(
        "SELECT device_uuid, latitude, longitude, geohash, agents_json, deleted "
        "FROM readings WHERE reading_id='a'").fetchone()
    assert row == (None, None, None, None, "[]", 1)
    v = db.verify_reading("a")
    assert v["deleted"] is True and v["integrityOk"] is None
    assert db.delete_reading("a") is None  # already deleted


def test_unknown_top_level_fields_preserved_but_reserved_ones_are_not():
    _fresh()
    rec = make_record("a")
    rec["ext"] = {"org.example": {"k": 1}}
    rec["readingId_evil"] = "ignored"
    db.insert_reading(rec)
    got = db.get_reading("a")
    assert got["ext"] == {"org.example": {"k": 1}}
    assert "readingId_evil" not in got


# ─── query / pagination ──────────────────────────────────────

def test_agent_filter_keeps_pagination_and_total_consistent():
    _fresh()
    for i in range(30):
        db.insert_reading(make_record(f"pm{i}", ts=NOW_US + i, agent="PM2_5"))
    for i in range(30):
        db.insert_reading(make_record(f"co{i}", ts=NOW_US + 100 + i, agent="CO"))
    page, total = db.query_readings(agent="pm2_5", limit=10, offset=10)
    assert total == 30
    assert len(page) == 10
    assert all(r["agents"][0]["agentId"] == "PM2_5" for r in page)


def test_negative_and_huge_limits_are_clamped_not_unbounded():
    _fresh()
    for i in range(5):
        db.insert_reading(make_record(f"r{i}", ts=NOW_US + i))
    rows, _ = db.query_readings(limit=-1)
    assert rows == []
    rows, _ = db.query_readings(limit=10**9, offset=-5)
    assert len(rows) == 5


def test_geohash_filter_treats_wildcards_literally():
    _fresh()
    db.insert_reading(make_record("a"))
    assert db.query_readings(geohash="%")[1] == 0
    assert db.query_readings(geohash="_____")[1] == 0
    assert db.query_readings(geohash=geo.encode_geohash(5.6037, -0.187, 5))[1] == 1


def test_geohash_prefix_query_uses_the_index():
    _fresh()
    db.insert_reading(make_record("a"))
    lo, hi = geo.prefix_bounds("s1v0g")
    plan = " ".join(str(tuple(r)) for r in sqlite3.connect(db.DB_PATH).execute(
        "EXPLAIN QUERY PLAN SELECT * FROM readings WHERE deleted=0 AND geohash>=? AND geohash<?",
        (lo, hi)))
    assert "idx_readings_geohash" in plan and "SCAN" not in plan.replace("SCAN readings USING", "")


# ─── sync cursor ─────────────────────────────────────────────

def test_sync_orders_by_ingest_sequence_and_resumes_without_gaps():
    _fresh()
    for i in range(7):
        db.insert_reading(make_record(f"r{i}", ts=NOW_US))  # identical timestamps
    seen, cursor = [], 0
    while True:
        items, cursor2 = db.get_readings_since(cursor, limit=3)
        if not items:
            break
        seen += [i["readingId"] for i in items]
        cursor = cursor2
    assert seen == [f"r{i}" for i in range(7)]  # no skips at page boundaries


def test_sync_delivers_late_arriving_old_readings():
    _fresh()
    db.insert_reading(make_record("new", ts=NOW_US))
    _, cursor = db.get_readings_since(0)
    db.insert_reading(make_record("late-offline", ts=NOW_US - 86_400_000_000))
    items, _ = db.get_readings_since(cursor)
    assert [i["readingId"] for i in items] == ["late-offline"]


def test_far_future_timestamp_cannot_stall_replication():
    _fresh()
    db.insert_reading(make_record("poison", ts=NOW_US + 10 * 365 * 86_400_000_000))
    _, cursor = db.get_readings_since(0)
    db.insert_reading(make_record("honest", ts=NOW_US))
    items, _ = db.get_readings_since(cursor)
    assert [i["readingId"] for i in items] == ["honest"]


def test_sync_propagates_deletions_as_content_free_tombstones():
    _fresh()
    db.insert_reading(make_record("a"))
    _, cursor = db.get_readings_since(0)
    db.delete_reading("a")
    items, _ = db.get_readings_since(cursor)
    assert len(items) == 1
    assert items[0]["deleted"] is True
    assert set(items[0]) == {"readingId", "deleted", "deletionProof"}


# ─── devices ─────────────────────────────────────────────────

def test_reregistering_a_device_uuid_is_rejected():
    _fresh()
    db.register_device("dev-x", "sha256:aaa")
    with pytest.raises(db.DeviceExistsError):
        db.register_device("dev-x", "sha256:bbb")
    assert db.validate_token("anything") is None


def test_cannot_register_uuid_that_already_has_anonymous_readings():
    _fresh()
    db.insert_reading(make_record("a", device="claimed-earlier"))
    with pytest.raises(db.DeviceExistsError):
        db.register_device("claimed-earlier", "sha256:aaa")


def test_last_seen_never_moves_backwards_and_count_batches():
    _fresh()
    db.register_device("d", "sha256:h")
    db.bump_device_seen("d", 200, count=3)
    db.bump_device_seen("d", 100)
    dev = db.get_device("d")
    assert dev["lastSeenUs"] == 200 and dev["readingCount"] == 4


# ─── nearby ──────────────────────────────────────────────────

def test_nearby_ranks_fresh_close_validated_over_stale_or_suspect():
    _fresh()
    db.insert_reading(make_record("good", ts=NOW_US - 60_000_000, quality="VALIDATED"))
    db.insert_reading(make_record("stale", ts=NOW_US - 3_000_000_000))
    db.insert_reading(make_record("suspect", ts=NOW_US - 60_000_000, quality="SUSPECT"))
    db.insert_reading(make_record("invalid", ts=NOW_US - 60_000_000, quality="INVALID"))
    out = db.get_nearby_readings(5.6037, -0.187, radius_m=2000, max_age_s=3600, limit=10)
    ids = [r["readingId"] for r in out]
    assert ids[0] == "good"
    assert "invalid" not in ids and "suspect" not in ids  # below default minQuality
    assert all("distanceM" in r and "relevanceScore" in r for r in out)


def test_nearby_finds_a_reading_within_radius_at_high_latitude():
    # Geohash cells are narrower away from the equator. At 65 N a fixed
    # precision-5 3x3 block is only ~2 km wide, so a 4 km search used to miss
    # readings that were well inside the radius.
    _fresh()
    lat, lon = 65.0, 25.0
    target_lat, target_lon = lat, lon + 3.0 / (111.32 * 0.4226)  # ~3 km east
    db.insert_reading(make_record("east", lat=target_lat, lon=target_lon))
    out = db.get_nearby_readings(lat, lon, radius_m=4000, max_age_s=3600, limit=5)
    assert [r["readingId"] for r in out] == ["east"]
    assert 2800 < out[0]["distanceM"] < 3200


def test_nearby_finds_reading_across_the_antimeridian():
    _fresh()
    db.insert_reading(make_record("w", lat=0.0, lon=-179.995))
    out = db.get_nearby_readings(0.0, 179.995, radius_m=2000, max_age_s=3600)
    assert [r["readingId"] for r in out] == ["w"]


def test_nearby_respects_agent_filter():
    _fresh()
    db.insert_reading(make_record("pm", agent="PM2_5"))
    db.insert_reading(make_record("co", agent="CO", ts=NOW_US - 1))
    out = db.get_nearby_readings(5.6037, -0.187, agent="co", limit=5)
    assert [r["readingId"] for r in out] == ["co"]


# ─── aggregates ──────────────────────────────────────────────

def test_aggregate_enforces_k_anonymity():
    _fresh()
    gh = geo.encode_geohash(5.6037, -0.187, 5)
    for i in range(4):
        db.insert_reading(make_record(f"r{i}", ts=NOW_US + i))
    assert db.get_aggregate(gh) is None
    db.insert_reading(make_record("r4", ts=NOW_US + 4))
    agg = db.get_aggregate(gh)
    assert agg["count"] == 5 and agg["kAnonymityMet"] is True


# ─── federated node registry ─────────────────────────────────

def test_node_cannot_be_redirected_to_a_new_url_by_a_third_party():
    _fresh()
    db.upsert_node("node-a", "https://a.example")
    with pytest.raises(db.NodeRegistryError):
        db.upsert_node("node-a", "https://evil.example")
    with pytest.raises(db.NodeRegistryError):
        db.upsert_node("node-b", "https://a.example")  # URL already listed
    db.upsert_node("node-a", "https://a.example", reading_count=5)  # refresh is fine
    assert db.get_nodes()[0]["reading_count"] == 5


# ─── migration from the pre-seq schema ───────────────────────

def test_old_database_is_migrated_in_place():
    db.DB_PATH = Path(tempfile.mkdtemp()) / "old.db"
    conn = sqlite3.connect(db.DB_PATH)
    conn.executescript("""
        CREATE TABLE readings (
            reading_id TEXT PRIMARY KEY, bxp_version TEXT NOT NULL, node_id TEXT NOT NULL,
            device_uuid TEXT, timestamp_iso TEXT NOT NULL, timestamp_us INTEGER NOT NULL,
            latitude REAL, longitude REAL, geohash TEXT, agents_json TEXT NOT NULL,
            readings_json TEXT NOT NULL, bxp_hri REAL, bxp_hri_level TEXT, quality_json TEXT,
            quality_flag TEXT, payload_hash TEXT, duration_s INTEGER DEFAULT 60,
            indoor_outdoor TEXT DEFAULT 'outdoor', deleted INTEGER DEFAULT 0,
            deletion_proof TEXT, created_at INTEGER NOT NULL);
    """)
    conn.execute(
        "INSERT INTO readings VALUES ('old1','2.0','n','d','t',1,5.6,-0.18,'s1v0g12',"
        "'[{\"agentId\": \"PM2_5\", \"value\": 1.0}]','{}',1.0,'CLEAN','{}','UNVALIDATED','h',60,"
        "'outdoor',0,NULL,1)")
    conn.commit()
    conn.close()
    db.init_db()
    db.init_db()  # idempotent
    rows, total = db.query_readings(agent="PM2_5")
    assert total == 1 and rows[0]["readingId"] == "old1"
    items, _ = db.get_readings_since(0)
    assert [i["readingId"] for i in items] == ["old1"]


# ─── geo.py ──────────────────────────────────────────────────

def test_geohash_known_vectors():
    # Widely published reference values.
    assert geo.encode_geohash(57.64911, 10.40744, 11) == "u4pruydqqvj"
    assert geo.encode_geohash(42.6, -5.6, 5) == "ezs42"
    assert geo.encode_geohash(0.0, 0.0, 5) == "s0000"


def test_geohash_decode_round_trip_contains_point():
    for lat, lon in [(5.6, -0.18), (-33.9, 151.2), (89.9, 179.9), (-89.9, -179.9)]:
        gh = geo.encode_geohash(lat, lon, 7)
        (a, b), (c, d) = geo.decode_bbox(gh)
        assert a <= lat <= b and c <= lon <= d


def test_decode_rejects_invalid_characters():
    with pytest.raises(ValueError):
        geo.decode_bbox("abcio")  # 'i', 'o' are not in the geohash alphabet


def test_prefix_bounds_match_exactly_the_prefixed_strings():
    lo, hi = geo.prefix_bounds("s1v0g")
    assert lo <= "s1v0g" < hi
    assert lo <= "s1v0gzzz" < hi
    assert not ("s1v0h" < hi and "s1v0h" >= lo)
    assert not (lo <= "s1v0" < hi and "s1v0" >= lo)


def test_precision_for_radius_shrinks_with_latitude_and_radius():
    assert geo.precision_for_radius(0.0, 1000) == 5
    assert geo.precision_for_radius(0.0, 4000) == 5
    assert geo.precision_for_radius(0.0, 50_000) < 5
    assert geo.precision_for_radius(65.0, 4000) < geo.precision_for_radius(0.0, 4000)
    assert geo.precision_for_radius(89.9, 4000) >= 1


def test_neighbors_are_nine_distinct_cells():
    assert len(geo.neighbors("s1v0g")) == 9


def test_haversine_known_distance():
    # London -> Paris is ~343.5 km.
    d = geo.haversine_m(51.5074, -0.1278, 48.8566, 2.3522)
    assert 342_000 < d < 345_000


def test_snap_to_cell_center_moves_less_than_one_cell():
    lat, lon = geo.snap_to_cell_center(5.60371, -0.18702, 5)
    assert geo.haversine_m(5.60371, -0.18702, lat, lon) < 4000
    assert geo.encode_geohash(lat, lon, 5) == geo.encode_geohash(5.60371, -0.18702, 5)
