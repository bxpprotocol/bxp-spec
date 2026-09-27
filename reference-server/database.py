"""
BXP Protocol — SQLite persistence layer
All submitted readings, devices, community reports, and deletion log
are stored here so server restarts don't wipe data.
"""

import sqlite3
import threading
import json
import time
import math
import hashlib
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).parent / "bxp_data.db"

_local = threading.local()


def _conn() -> sqlite3.Connection:
    if not hasattr(_local, "conn") or _local.conn is None:
        conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        _local.conn = conn
    return _local.conn


_write_lock = threading.Lock()


def init_db():
    """Create tables if they don't exist (idempotent)."""
    conn = _conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS readings (
            reading_id      TEXT PRIMARY KEY,
            bxp_version     TEXT NOT NULL,
            node_id         TEXT NOT NULL,
            device_uuid     TEXT,
            timestamp_iso   TEXT NOT NULL,
            timestamp_us    INTEGER NOT NULL,
            latitude        REAL,
            longitude       REAL,
            geohash         TEXT,
            agents_json     TEXT NOT NULL,
            readings_json   TEXT NOT NULL,
            bxp_hri         REAL,
            bxp_hri_level   TEXT,
            quality_json    TEXT,
            quality_flag    TEXT,
            payload_hash    TEXT,
            duration_s      INTEGER DEFAULT 60,
            indoor_outdoor  TEXT DEFAULT 'outdoor',
            deleted         INTEGER DEFAULT 0,
            deletion_proof  TEXT,
            created_at      INTEGER NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_readings_geohash
            ON readings (geohash);
        CREATE INDEX IF NOT EXISTS idx_readings_ts
            ON readings (timestamp_us);
        CREATE INDEX IF NOT EXISTS idx_readings_quality
            ON readings (quality_flag);
        CREATE INDEX IF NOT EXISTS idx_readings_device
            ON readings (device_uuid);

        CREATE TABLE IF NOT EXISTS devices (
            device_uuid     TEXT PRIMARY KEY,
            token_hash      TEXT UNIQUE,
            label           TEXT,
            owner_hash      TEXT,
            registered_at   INTEGER NOT NULL,
            last_seen_us    INTEGER,
            reading_count   INTEGER DEFAULT 0,
            active          INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS community_reports (
            report_id       TEXT PRIMARY KEY,
            geohash         TEXT NOT NULL,
            latitude        REAL,
            longitude       REAL,
            timestamp_iso   TEXT NOT NULL,
            timestamp_us    INTEGER NOT NULL,
            report_type     TEXT NOT NULL,
            description     TEXT,
            severity        TEXT,
            submitter_hash  TEXT,
            verified        INTEGER DEFAULT 0,
            created_at      INTEGER NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_reports_geohash
            ON community_reports (geohash);

        CREATE TABLE IF NOT EXISTS deletion_log (
            reading_id      TEXT PRIMARY KEY,
            deleted_at      INTEGER NOT NULL,
            deletion_proof  TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS rate_limit_log (
            ip_key          TEXT NOT NULL,
            window_start    INTEGER NOT NULL,
            count           INTEGER DEFAULT 0,
            PRIMARY KEY (ip_key, window_start)
        );

        CREATE TABLE IF NOT EXISTS federated_nodes (
            node_id         TEXT PRIMARY KEY,
            base_url        TEXT UNIQUE NOT NULL,
            last_seen       INTEGER,
            bxp_version     TEXT,
            node_type       TEXT,
            reading_count   INTEGER DEFAULT 0,
            active          INTEGER DEFAULT 1
        );
    """)
    conn.commit()


# ─── Readings ────────────────────────────────────────────────

def insert_reading(record: dict):
    with _write_lock:
        conn = _conn()
        conn.execute("""
            INSERT OR REPLACE INTO readings
            (reading_id, bxp_version, node_id, device_uuid,
             timestamp_iso, timestamp_us, latitude, longitude, geohash,
             agents_json, readings_json, bxp_hri, bxp_hri_level,
             quality_json, quality_flag, payload_hash,
             duration_s, indoor_outdoor, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            record["readingId"],
            record.get("bxpVersion", "2.0"),
            record.get("nodeId", ""),
            record.get("deviceUuid"),
            record.get("timestamp", ""),
            record.get("timestampUs", 0),
            record.get("latitude"),
            record.get("longitude"),
            record.get("geohash"),
            json.dumps(record.get("agents", [])),
            json.dumps(record.get("readings", {})),
            record.get("bxpHri"),
            record.get("bxpHriLevel"),
            json.dumps(record.get("quality", {})),
            record.get("qualityFlag"),
            record.get("payloadHash"),
            record.get("durationS", 60),
            record.get("indoorOutdoor", "outdoor"),
            int(time.time()),
        ))
        conn.commit()


def get_reading(reading_id: str) -> Optional[dict]:
    conn = _conn()
    row = conn.execute(
        "SELECT * FROM readings WHERE reading_id=? AND deleted=0",
        (reading_id,)
    ).fetchone()
    return _row_to_reading(row) if row else None


def delete_reading(reading_id: str) -> Optional[str]:
    """
    Soft-delete a reading. Returns deletion proof (SHA-256 of
    reading_id + deleted_at) or None if reading not found.
    """
    with _write_lock:
        conn = _conn()
        row = conn.execute(
            "SELECT reading_id, payload_hash FROM readings "
            "WHERE reading_id=? AND deleted=0",
            (reading_id,)
        ).fetchone()
        if not row:
            return None
        deleted_at = int(time.time())
        proof = "sha256:" + hashlib.sha256(
            f"{reading_id}:{deleted_at}".encode()
        ).hexdigest()
        conn.execute(
            "UPDATE readings SET deleted=1, deletion_proof=? "
            "WHERE reading_id=?",
            (proof, reading_id)
        )
        conn.execute(
            "INSERT OR REPLACE INTO deletion_log "
            "(reading_id, deleted_at, deletion_proof) VALUES (?,?,?)",
            (reading_id, deleted_at, proof)
        )
        conn.commit()
        return proof


def verify_reading(reading_id: str) -> Optional[dict]:
    conn = _conn()
    row = conn.execute(
        "SELECT * FROM readings WHERE reading_id=?",
        (reading_id,)
    ).fetchone()
    if not row:
        return None
    record = _row_to_reading(row)
    claimed = record.get("payloadHash", "")
    # Re-compute hash over stable fields
    check = {k: v for k, v in record.items()
             if k not in ("payloadHash",)}
    import json as _json
    payload_str = _json.dumps(check, sort_keys=True,
                              separators=(',', ':'), default=str)
    computed = "sha256:" + hashlib.sha256(
        payload_str.encode()
    ).hexdigest()
    return {
        "readingId": reading_id,
        "integrityOk": computed == claimed,
        "claimedHash": claimed,
        "computedHash": computed,
        "deleted": bool(row["deleted"]),
        "deletionProof": row["deletion_proof"],
    }


def query_readings(
    geohash: Optional[str] = None,
    from_ts: Optional[int] = None,
    to_ts: Optional[int] = None,
    agent: Optional[str] = None,
    quality: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list, int]:
    """Returns (readings, total_count)."""
    conn = _conn()
    clauses = ["deleted=0"]
    params: list = []

    if geohash:
        clauses.append("geohash LIKE ?")
        params.append(geohash + "%")
    if from_ts:
        clauses.append("timestamp_us >= ?")
        params.append(from_ts)
    if to_ts:
        clauses.append("timestamp_us <= ?")
        params.append(to_ts)
    if quality:
        clauses.append("quality_flag = ?")
        params.append(quality.upper())

    where = " AND ".join(clauses)
    total = conn.execute(
        f"SELECT COUNT(*) FROM readings WHERE {where}", params
    ).fetchone()[0]

    rows = conn.execute(
        f"SELECT * FROM readings WHERE {where} "
        "ORDER BY timestamp_us DESC LIMIT ? OFFSET ?",
        params + [limit, offset]
    ).fetchall()

    results = [_row_to_reading(r) for r in rows]

    # Post-filter by agent (can't do in SQL easily)
    if agent:
        agent_upper = agent.upper()
        results = [r for r in results
                   if any(a.get("agentId", "").upper() == agent_upper
                          for a in r.get("agents", []))]

    return results, total


def get_geohash_latest(geohash: str) -> Optional[dict]:
    conn = _conn()
    row = conn.execute(
        "SELECT * FROM readings WHERE geohash LIKE ? AND deleted=0 "
        "ORDER BY timestamp_us DESC LIMIT 1",
        (geohash[:7] + "%",)
    ).fetchone()
    return _row_to_reading(row) if row else None


def get_geohash_history(geohash: str, limit: int = 50) -> list:
    conn = _conn()
    rows = conn.execute(
        "SELECT * FROM readings WHERE geohash LIKE ? AND deleted=0 "
        "ORDER BY timestamp_us DESC LIMIT ?",
        (geohash[:7] + "%", limit)
    ).fetchall()
    return [_row_to_reading(r) for r in rows]


def get_aggregate(geohash: str, from_ts: Optional[int] = None,
                  to_ts: Optional[int] = None) -> Optional[dict]:
    """
    Privacy-safe aggregate: only returns if k≥5 readings (§9).
    Returns min/max/avg HRI over the time window.
    """
    conn = _conn()
    clauses = ["geohash LIKE ?", "deleted=0"]
    params: list = [geohash[:5] + "%"]
    if from_ts:
        clauses.append("timestamp_us >= ?")
        params.append(from_ts)
    if to_ts:
        clauses.append("timestamp_us <= ?")
        params.append(to_ts)
    where = " AND ".join(clauses)

    row = conn.execute(
        f"SELECT COUNT(*) as cnt, MIN(bxp_hri) as min_hri, "
        f"MAX(bxp_hri) as max_hri, AVG(bxp_hri) as avg_hri, "
        f"MIN(timestamp_us) as first_ts, MAX(timestamp_us) as last_ts "
        f"FROM readings WHERE {where}",
        params
    ).fetchone()

    if not row or row["cnt"] < 5:
        return None  # k-anonymity: minimum 5 readings required

    return {
        "geohash": geohash[:5],
        "count": row["cnt"],
        "hri": {
            "min": round(row["min_hri"] or 0, 1),
            "max": round(row["max_hri"] or 0, 1),
            "avg": round(row["avg_hri"] or 0, 1),
        },
        "firstTimestampUs": row["first_ts"],
        "lastTimestampUs": row["last_ts"],
        "kAnonymityMet": True,
        "kMinimum": 5,
    }


def reading_count() -> int:
    conn = _conn()
    return conn.execute(
        "SELECT COUNT(*) FROM readings WHERE deleted=0"
    ).fetchone()[0]


# ─── Geo helpers for /nearby (spec §7 Stage 6, §8.2.1) ────────
#
# Small, self-contained geohash encode/decode/neighbor + haversine
# distance — duplicated from bxp_sdk.encode_geohash / server._encode_geohash
# rather than imported, to keep this module free of a dependency on the
# server or SDK. If you change the geohash bit-encoding algorithm, it
# must change identically in all three places.

_BASE32 = "0123456789bcdefghjkmnpqrstuvwxyz"


def _encode_geohash(lat: float, lon: float, precision: int = 7) -> str:
    lat_range, lon_range = [-90.0, 90.0], [-180.0, 180.0]
    geohash, bit, ch, even = [], 0, 0, True
    bits = [16, 8, 4, 2, 1]
    while len(geohash) < precision:
        if even:
            mid = (lon_range[0] + lon_range[1]) / 2
            if lon >= mid:
                ch |= bits[bit]; lon_range[0] = mid
            else:
                lon_range[1] = mid
        else:
            mid = (lat_range[0] + lat_range[1]) / 2
            if lat >= mid:
                ch |= bits[bit]; lat_range[0] = mid
            else:
                lat_range[1] = mid
        even = not even
        if bit < 4:
            bit += 1
        else:
            geohash.append(_BASE32[ch]); bit = 0; ch = 0
    return "".join(geohash)


def _decode_geohash_bbox(gh: str):
    """Returns ([lat_min, lat_max], [lon_min, lon_max])."""
    lat_range, lon_range = [-90.0, 90.0], [-180.0, 180.0]
    even = True
    for char in gh:
        idx = _BASE32.index(char)
        for bit in (16, 8, 4, 2, 1):
            if even:
                mid = (lon_range[0] + lon_range[1]) / 2
                if idx & bit:
                    lon_range[0] = mid
                else:
                    lon_range[1] = mid
            else:
                mid = (lat_range[0] + lat_range[1]) / 2
                if idx & bit:
                    lat_range[0] = mid
                else:
                    lat_range[1] = mid
            even = not even
    return lat_range, lon_range


def _geohash_neighbors(gh: str) -> set:
    """
    The cell itself plus its 8 neighbors, at the same precision as `gh`.
    Per spec §8.2.1, a geohash-5 cell + its 8 neighbors always fully
    covers a search radius up to ~4.9km, which is why /nearby's default
    radiusM (2000) and this expansion are safe together.
    """
    lat_range, lon_range = _decode_geohash_bbox(gh)
    center_lat = (lat_range[0] + lat_range[1]) / 2
    center_lon = (lon_range[0] + lon_range[1]) / 2
    lat_err = lat_range[1] - lat_range[0]
    lon_err = lon_range[1] - lon_range[0]
    precision = len(gh)
    cells = set()
    for dlat in (-1, 0, 1):
        for dlon in (-1, 0, 1):
            nlat = max(-90.0, min(90.0, center_lat + dlat * lat_err))
            nlon = ((center_lon + dlon * lon_err + 180) % 360) - 180
            cells.add(_encode_geohash(nlat, nlon, precision))
    return cells


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in meters."""
    r = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (math.sin(dphi / 2) ** 2
         + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2)
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


# Spec's relative ordering (§7 Stage 6): VALIDATED > UNVALIDATED > SUSPECT;
# INVALID excluded regardless of minQuality.
QUALITY_RANK = {"INVALID": -1, "SUSPECT": 0, "UNVALIDATED": 1, "VALIDATED": 2}


def get_nearby_readings(
    lat: float, lon: float,
    radius_m: int = 2000, max_age_s: int = 3600,
    agent: Optional[str] = None, min_quality: str = "UNVALIDATED",
    limit: int = 1, now_us: Optional[int] = None,
) -> list:
    """
    Relevance-ranked nearby lookup (spec §8.2.1). The ranking formula
    below — a blend of distance, freshness, and a quality multiplier —
    is deliberately not part of the wire contract (§7 Stage 6: "the exact
    scoring weights are an implementation detail"); only the parameters
    and the general behavior ("closer+fresher+better-quality ranks
    higher, no single factor dominates") are.
    """
    conn = _conn()
    now_us = now_us if now_us is not None else int(time.time() * 1_000_000)
    min_ts = now_us - int(max_age_s) * 1_000_000
    min_rank = QUALITY_RANK.get((min_quality or "UNVALIDATED").upper(), 1)

    center_gh = _encode_geohash(lat, lon, 5)
    cells = _geohash_neighbors(center_gh)

    clauses = ["deleted=0", "timestamp_us >= ?",
               "latitude IS NOT NULL", "longitude IS NOT NULL"]
    params: list = [min_ts]
    cell_clause = " OR ".join(["geohash LIKE ?"] * len(cells))
    clauses.append(f"({cell_clause})")
    params.extend(c + "%" for c in cells)

    where = " AND ".join(clauses)
    rows = conn.execute(f"SELECT * FROM readings WHERE {where}", params).fetchall()
    candidates = [_row_to_reading(r) for r in rows]

    candidates = [
        c for c in candidates
        if QUALITY_RANK.get((c.get("qualityFlag") or "UNVALIDATED").upper(), 0) >= max(min_rank, 0)
    ]

    if agent:
        agent_upper = agent.upper()
        candidates = [
            c for c in candidates
            if any(a.get("agentId", "").upper() == agent_upper
                   for a in c.get("agents", []))
        ]

    scored = []
    for c in candidates:
        dist_m = _haversine_m(lat, lon, c["latitude"], c["longitude"])
        if dist_m > radius_m:
            continue
        age_s = max(0.0, (now_us - c["timestampUs"]) / 1_000_000)
        distance_score = max(0.0, 1 - dist_m / radius_m) if radius_m > 0 else 0.0
        freshness_score = max(0.0, 1 - age_s / max_age_s) if max_age_s > 0 else 0.0
        quality_weight = {"VALIDATED": 1.15, "UNVALIDATED": 1.0, "SUSPECT": 0.6}.get(
            c.get("qualityFlag"), 1.0
        )
        relevance = (0.5 * distance_score + 0.5 * freshness_score) * quality_weight
        c["distanceM"] = round(dist_m, 1)
        c["relevanceScore"] = round(relevance, 4)
        scored.append(c)

    scored.sort(key=lambda c: c["relevanceScore"], reverse=True)
    return scored[:limit]


# ─── Federation pull (spec §7 Stage 7, §8.2.2) ────────────────

def get_readings_since(since_ts_us: int, limit: int = 500) -> tuple[list, int]:
    """
    Returns (readings, nextSinceTs) — readings created strictly after
    since_ts_us, ordered oldest-first so a caller can resume from
    nextSinceTs without gaps or dupes across paginated pulls.
    """
    conn = _conn()
    limit = min(max(limit, 1), 2000)
    rows = conn.execute(
        "SELECT * FROM readings WHERE timestamp_us > ? AND deleted=0 "
        "ORDER BY timestamp_us ASC LIMIT ?",
        (since_ts_us, limit)
    ).fetchall()
    results = [_row_to_reading(r) for r in rows]
    next_since_ts = results[-1]["timestampUs"] if results else since_ts_us
    return results, next_since_ts


def _row_to_reading(row: sqlite3.Row) -> dict:
    try:
        agents = json.loads(row["agents_json"])
    except Exception:
        agents = []
    try:
        readings_dict = json.loads(row["readings_json"])
    except Exception:
        readings_dict = {}
    try:
        quality = json.loads(row["quality_json"])
    except Exception:
        quality = {}

    return {
        "readingId":    row["reading_id"],
        "bxpVersion":   row["bxp_version"],
        "nodeId":       row["node_id"],
        "deviceUuid":   row["device_uuid"],
        "timestamp":    row["timestamp_iso"],
        "timestampUs":  row["timestamp_us"],
        "latitude":     row["latitude"],
        "longitude":    row["longitude"],
        "geohash":      row["geohash"],
        "location": {
            "latitude":  row["latitude"],
            "longitude": row["longitude"],
            "geohash":   row["geohash"],
        },
        "agents":       agents,
        "readings":     readings_dict,
        "bxpHri":       row["bxp_hri"],
        "bxpHriLevel":  row["bxp_hri_level"],
        "quality":      quality,
        "qualityFlag":  row["quality_flag"],
        "payloadHash":  row["payload_hash"],
        "durationS":    row["duration_s"],
        "indoorOutdoor": row["indoor_outdoor"],
    }


# ─── Devices ─────────────────────────────────────────────────

def register_device(device_uuid: str, token_hash: str,
                    label: Optional[str] = None,
                    owner_hash: Optional[str] = None) -> dict:
    with _write_lock:
        conn = _conn()
        now = int(time.time())
        conn.execute("""
            INSERT OR REPLACE INTO devices
            (device_uuid, token_hash, label, owner_hash,
             registered_at, active)
            VALUES (?,?,?,?,?,1)
        """, (device_uuid, token_hash, label, owner_hash, now))
        conn.commit()
    return get_device(device_uuid)


def get_device(device_uuid: str) -> Optional[dict]:
    conn = _conn()
    row = conn.execute(
        "SELECT * FROM devices WHERE device_uuid=?",
        (device_uuid,)
    ).fetchone()
    if not row:
        return None
    return {
        "deviceUuid":   row["device_uuid"],
        "label":        row["label"],
        "registeredAt": row["registered_at"],
        "lastSeenUs":   row["last_seen_us"],
        "readingCount": row["reading_count"],
        "active":       bool(row["active"]),
    }


def validate_token(token: str) -> Optional[str]:
    """Returns device_uuid if token is valid, else None."""
    token_hash = "sha256:" + hashlib.sha256(token.encode()).hexdigest()
    conn = _conn()
    row = conn.execute(
        "SELECT device_uuid FROM devices "
        "WHERE token_hash=? AND active=1",
        (token_hash,)
    ).fetchone()
    return row["device_uuid"] if row else None


def bump_device_seen(device_uuid: str, ts_us: int):
    with _write_lock:
        conn = _conn()
        conn.execute(
            "UPDATE devices SET last_seen_us=?, "
            "reading_count=reading_count+1 WHERE device_uuid=?",
            (ts_us, device_uuid)
        )
        conn.commit()


# ─── Community Reports ───────────────────────────────────────

def insert_report(report: dict):
    with _write_lock:
        conn = _conn()
        conn.execute("""
            INSERT OR REPLACE INTO community_reports
            (report_id, geohash, latitude, longitude,
             timestamp_iso, timestamp_us, report_type,
             description, severity, submitter_hash, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (
            report["reportId"],
            report.get("geohash", ""),
            report.get("latitude"),
            report.get("longitude"),
            report.get("timestamp", ""),
            report.get("timestampUs", 0),
            report.get("reportType", "observation"),
            report.get("description"),
            report.get("severity"),
            report.get("submitterHash"),
            int(time.time()),
        ))
        conn.commit()


def query_reports(geohash: Optional[str] = None,
                  limit: int = 50) -> list:
    conn = _conn()
    if geohash:
        rows = conn.execute(
            "SELECT * FROM community_reports WHERE geohash LIKE ? "
            "ORDER BY timestamp_us DESC LIMIT ?",
            (geohash + "%", limit)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM community_reports "
            "ORDER BY timestamp_us DESC LIMIT ?",
            (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


# ─── Federated nodes ─────────────────────────────────────────

def upsert_node(node_id: str, base_url: str, bxp_version: str = "2.0",
                node_type: str = "reference",
                reading_count: int = 0):
    with _write_lock:
        conn = _conn()
        conn.execute("""
            INSERT INTO federated_nodes
            (node_id, base_url, last_seen, bxp_version,
             node_type, reading_count, active)
            VALUES (?,?,?,?,?,?,1)
            ON CONFLICT(node_id) DO UPDATE SET
              last_seen=excluded.last_seen,
              bxp_version=excluded.bxp_version,
              reading_count=excluded.reading_count,
              active=1
        """, (
            node_id, base_url, int(time.time()),
            bxp_version, node_type, reading_count
        ))
        conn.commit()


def get_nodes(active_only: bool = True) -> list:
    conn = _conn()
    q = "SELECT * FROM federated_nodes"
    if active_only:
        q += " WHERE active=1"
    q += " ORDER BY last_seen DESC"
    return [dict(r) for r in conn.execute(q).fetchall()]
