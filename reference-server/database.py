"""
BXP Protocol — SQLite persistence layer
All submitted readings, devices, community reports, and deletion log
are stored here so server restarts don't wipe data.
"""

import sqlite3
import threading
import json
import time
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
