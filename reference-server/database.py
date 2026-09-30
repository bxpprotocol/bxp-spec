"""
BXP reference node - SQLite persistence layer.

Design notes (why this module looks the way it does):

* One connection per thread, opened lazily. Writes go through `_tx()`, which
  serialises in-process writers with a lock AND takes SQLite's write lock with
  BEGIN IMMEDIATE, so multi-statement writes are atomic and the ingest
  sequence (`seq`) stays gap-free and monotonic even with several worker
  processes sharing one database file.
* `seq` is the federation cursor. It is assigned at ingestion (and re-assigned
  when a reading is deleted, so the deletion propagates as a tombstone). It is
  NOT derived from the observation timestamp: a device can report any
  timestamp, so a timestamp cursor lets one far-future reading permanently
  stall replication and silently skips late-arriving offline readings.
* Readings are insert-if-absent. `INSERT OR REPLACE` would let a later
  submission overwrite (or resurrect a deleted) reading.
* Deleting a reading scrubs its content, not just a flag: SPEC.md section 9.1
  promises deletion is irreversible.
* Geohash prefix matches use index-friendly range predicates (see
  geo.prefix_bounds), not LIKE.
"""

import hashlib
import json
import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

import geo

# Override with BXP_DB_PATH to keep data outside the source tree (e.g. a
# Docker volume mounted at /data) so upgrading the image never shadows code.
DB_PATH = Path(os.environ.get("BXP_DB_PATH") or Path(__file__).parent / "bxp_data.db")

MAX_PAGE = 1000          # hard ceiling for any single page of results
MAX_NEARBY_CANDIDATES = 5000
MAX_REGISTERED_NODES = 1000
K_ANONYMITY_MIN = 5

_local = threading.local()
_write_lock = threading.Lock()


class DeviceExistsError(Exception):
    """A device UUID is already registered, or already appears on stored readings."""


class NodeRegistryError(ValueError):
    """A federated node announcement was rejected (conflict or registry full)."""


def _conn() -> sqlite3.Connection:
    # Reconnect if DB_PATH changed (tests point it at a temp file per test).
    if getattr(_local, "conn", None) is None or getattr(_local, "path", None) != DB_PATH:
        old = getattr(_local, "conn", None)
        if old is not None:
            old.close()
        # isolation_level=None: autocommit; transactions are explicit (see _tx).
        conn = sqlite3.connect(str(DB_PATH), check_same_thread=False,
                               isolation_level=None, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=10000")
        # Zero freed pages so deleted readings cannot be recovered from the file.
        conn.execute("PRAGMA secure_delete=ON")
        _local.conn, _local.path = conn, DB_PATH
    return _local.conn


@contextmanager
def _tx() -> Iterator[sqlite3.Connection]:
    with _write_lock:
        conn = _conn()
        conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        else:
            conn.execute("COMMIT")


def _clamp_page(limit: int, offset: int = 0) -> tuple[int, int]:
    return max(0, min(int(limit), MAX_PAGE)), max(0, int(offset))


# ─── Schema ──────────────────────────────────────────────────

_SCHEMA = [
    """CREATE TABLE IF NOT EXISTS readings (
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
        created_at      INTEGER NOT NULL,
        seq             INTEGER,
        agent_ids       TEXT NOT NULL DEFAULT ',',
        extra_json      TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS devices (
        device_uuid     TEXT PRIMARY KEY,
        token_hash      TEXT UNIQUE,
        label           TEXT,
        owner_hash      TEXT,
        registered_at   INTEGER NOT NULL,
        last_seen_us    INTEGER,
        reading_count   INTEGER DEFAULT 0,
        active          INTEGER DEFAULT 1
    )""",
    """CREATE TABLE IF NOT EXISTS community_reports (
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
    )""",
    """CREATE TABLE IF NOT EXISTS deletion_log (
        reading_id      TEXT PRIMARY KEY,
        deleted_at      INTEGER NOT NULL,
        deletion_proof  TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS federated_nodes (
        node_id         TEXT PRIMARY KEY,
        base_url        TEXT UNIQUE NOT NULL,
        last_seen       INTEGER,
        bxp_version     TEXT,
        node_type       TEXT,
        reading_count   INTEGER DEFAULT 0,
        active          INTEGER DEFAULT 1
    )""",
]

# Created after column migrations so they can reference the newer columns.
_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_readings_geohash ON readings (geohash, timestamp_us)",
    "CREATE INDEX IF NOT EXISTS idx_readings_ts      ON readings (timestamp_us)",
    "CREATE INDEX IF NOT EXISTS idx_readings_quality ON readings (quality_flag)",
    "CREATE INDEX IF NOT EXISTS idx_readings_device  ON readings (device_uuid)",
    "CREATE INDEX IF NOT EXISTS idx_readings_seq     ON readings (seq)",
    "CREATE INDEX IF NOT EXISTS idx_reports_geohash  ON community_reports (geohash)",
]


def init_db() -> None:
    """Create tables and migrate older databases in place (idempotent)."""
    with _tx() as conn:
        for statement in _SCHEMA:
            conn.execute(statement)
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(readings)")}
        if "seq" not in cols:
            conn.execute("ALTER TABLE readings ADD COLUMN seq INTEGER")
        if "agent_ids" not in cols:
            conn.execute("ALTER TABLE readings ADD COLUMN agent_ids TEXT NOT NULL DEFAULT ','")
        if "extra_json" not in cols:
            conn.execute("ALTER TABLE readings ADD COLUMN extra_json TEXT")
        # Backfill rows written before these columns existed.
        conn.execute("UPDATE readings SET seq = rowid WHERE seq IS NULL")
        for row in conn.execute("SELECT reading_id, agents_json FROM readings "
                                "WHERE agent_ids = ',' AND deleted = 0").fetchall():
            ids = _agent_ids_column(_loads(row["agents_json"], []))
            if ids != ",":
                conn.execute("UPDATE readings SET agent_ids=? WHERE reading_id=?",
                             (ids, row["reading_id"]))
        for statement in _INDEXES:
            conn.execute(statement)


def _loads(text: Optional[str], default):
    try:
        return json.loads(text) if text else default
    except (TypeError, ValueError):
        return default


def _agent_ids_column(agents: list) -> str:
    """',PM2_5,CO,' - delimiter-wrapped so membership is an exact-match instr()."""
    ids = sorted({str(a.get("agentId", "")).upper() for a in agents if isinstance(a, dict)} - {""})
    return "," + ",".join(ids) + "," if ids else ","


_NEXT_SEQ = "(SELECT COALESCE(MAX(seq), 0) + 1 FROM readings)"


# ─── Readings ────────────────────────────────────────────────

_INSERT_READING = (
    "INSERT OR IGNORE INTO readings "
    "(reading_id, bxp_version, node_id, device_uuid, "
    "timestamp_iso, timestamp_us, latitude, longitude, geohash, "
    "agents_json, readings_json, bxp_hri, bxp_hri_level, "
    "quality_json, quality_flag, payload_hash, "
    "duration_s, indoor_outdoor, created_at, seq, agent_ids, extra_json) "
    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?," + _NEXT_SEQ + ",?,?)"
)

# Top-level record keys preserved verbatim if the client sent them
# (SPEC.md section 5.7: ignore-and-preserve; section 5.9: `ext`).
PRESERVED_EXTRA_KEYS = ("ext", "context", "signature", "sourceQuality")


def _reading_params(record: dict) -> tuple:
    agents = record.get("agents", [])
    extra = {k: record[k] for k in PRESERVED_EXTRA_KEYS if k in record}
    return (
        record["readingId"],
        record.get("bxpVersion", "2.0"),
        record.get("nodeId", ""),
        record.get("deviceUuid"),
        record.get("timestamp", ""),
        record.get("timestampUs", 0),
        record.get("latitude"),
        record.get("longitude"),
        record.get("geohash"),
        json.dumps(agents),
        json.dumps(record.get("readings", {})),
        record.get("bxpHri"),
        record.get("bxpHriLevel"),
        json.dumps(record.get("quality", {})),
        record.get("qualityFlag"),
        record.get("payloadHash"),
        record.get("durationS", 60),
        record.get("indoorOutdoor", "outdoor"),
        int(time.time()),
        _agent_ids_column(agents),
        json.dumps(extra) if extra else None,
    )


def insert_readings(records: list[dict]) -> list[bool]:
    """
    Insert a batch atomically. Returns one flag per record: True if stored,
    False if a reading with that ID already existed (live OR deleted - an
    existing reading is never overwritten or resurrected).
    """
    with _tx() as conn:
        return [conn.execute(_INSERT_READING, _reading_params(r)).rowcount == 1
                for r in records]


def insert_reading(record: dict) -> bool:
    return insert_readings([record])[0]


def get_reading(reading_id: str) -> Optional[dict]:
    row = _conn().execute(
        "SELECT * FROM readings WHERE reading_id=? AND deleted=0", (reading_id,)
    ).fetchone()
    return _row_to_reading(row) if row else None


def delete_reading(reading_id: str) -> Optional[str]:
    """
    Irreversibly delete a reading: its content is scrubbed, a tombstone remains
    (so the deletion replicates to federated peers), and a proof is returned.
    Returns None if the reading does not exist or is already deleted.
    """
    with _tx() as conn:
        row = conn.execute(
            "SELECT reading_id FROM readings WHERE reading_id=? AND deleted=0",
            (reading_id,),
        ).fetchone()
        if not row:
            return None
        deleted_at = int(time.time())
        proof = "sha256:" + hashlib.sha256(f"{reading_id}:{deleted_at}".encode()).hexdigest()
        sql = ("UPDATE readings SET deleted=1, deletion_proof=?, seq=" + _NEXT_SEQ + ", "
            "device_uuid=NULL, latitude=NULL, longitude=NULL, geohash=NULL, "
            "agents_json='[]', readings_json='{}', quality_json='{}', "
            "agent_ids=',', extra_json=NULL, bxp_hri=NULL, payload_hash=NULL "
            "WHERE reading_id=?")  # noqa: S608 - _NEXT_SEQ is constant
        conn.execute(sql, (proof, reading_id))
        conn.execute(
            "INSERT OR REPLACE INTO deletion_log (reading_id, deleted_at, deletion_proof) "
            "VALUES (?,?,?)",
            (reading_id, deleted_at, proof),
        )
        return proof


def canonical_payload_hash(record: dict) -> str:
    """SHA-256 over the record minus its own hash (SPEC.md section 5.5, canonical JSON)."""
    body = {k: v for k, v in record.items() if k != "payloadHash"}
    text = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(text.encode()).hexdigest()


def verify_reading(reading_id: str) -> Optional[dict]:
    row = _conn().execute("SELECT * FROM readings WHERE reading_id=?", (reading_id,)).fetchone()
    if not row:
        return None
    if row["deleted"]:
        return {"readingId": reading_id, "integrityOk": None, "claimedHash": None,
                "computedHash": None, "deleted": True,
                "deletionProof": row["deletion_proof"]}
    record = _row_to_reading(row)
    claimed = record.get("payloadHash", "")
    computed = canonical_payload_hash(record)
    return {"readingId": reading_id, "integrityOk": computed == claimed,
            "claimedHash": claimed, "computedHash": computed,
            "deleted": False, "deletionProof": None}


def _prefix_clause(column: str, prefix: str) -> tuple[str, list]:
    lo, hi = geo.prefix_bounds(prefix)
    return f"({column} >= ? AND {column} < ?)", [lo, hi]


def query_readings(
    geohash: Optional[str] = None,
    from_ts: Optional[int] = None,
    to_ts: Optional[int] = None,
    agent: Optional[str] = None,
    quality: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list, int]:
    """Returns (readings, total_matching). Every filter is applied in SQL so
    `total`, `limit` and `offset` stay consistent with each other."""
    limit, offset = _clamp_page(limit, offset)
    clauses, params = ["deleted=0"], []
    if geohash:
        clause, p = _prefix_clause("geohash", geohash)
        clauses.append(clause)
        params += p
    if from_ts is not None:
        clauses.append("timestamp_us >= ?")
        params.append(from_ts)
    if to_ts is not None:
        clauses.append("timestamp_us <= ?")
        params.append(to_ts)
    if quality:
        clauses.append("quality_flag = ?")
        params.append(quality.upper())
    if agent:
        clauses.append("instr(agent_ids, ?) > 0")
        params.append(f",{agent.upper()},")
    where = " AND ".join(clauses)
    conn = _conn()
    total = conn.execute(
        f"SELECT COUNT(*) FROM readings WHERE {where}", params  # noqa: S608 - literal fragments, bound values
    ).fetchone()[0]
    rows = conn.execute(
        f"SELECT * FROM readings WHERE {where} "  # noqa: S608
        "ORDER BY timestamp_us DESC LIMIT ? OFFSET ?",
        params + [limit, offset],
    ).fetchall()
    return [_row_to_reading(r) for r in rows], total


def get_geohash_latest(geohash: str) -> Optional[dict]:
    rows = get_geohash_history(geohash, 1)
    return rows[0] if rows else None


def get_geohash_history(geohash: str, limit: int = 50) -> list:
    limit, _ = _clamp_page(limit)
    clause, params = _prefix_clause("geohash", geohash[:7])
    rows = _conn().execute(
        f"SELECT * FROM readings WHERE {clause} AND deleted=0 "  # noqa: S608
        "ORDER BY timestamp_us DESC LIMIT ?",
        params + [limit],
    ).fetchall()
    return [_row_to_reading(r) for r in rows]


def get_aggregate(geohash: str, from_ts: Optional[int] = None,
                  to_ts: Optional[int] = None) -> Optional[dict]:
    """Privacy-safe aggregate (SPEC.md section 9): None unless >= 5 readings contribute."""
    clause, params = _prefix_clause("geohash", geohash[:5])
    clauses = [clause, "deleted=0", "bxp_hri IS NOT NULL"]
    if from_ts is not None:
        clauses.append("timestamp_us >= ?")
        params.append(from_ts)
    if to_ts is not None:
        clauses.append("timestamp_us <= ?")
        params.append(to_ts)
    row = _conn().execute(
        "SELECT COUNT(*) AS cnt, MIN(bxp_hri) AS min_hri, MAX(bxp_hri) AS max_hri, "  # noqa: S608
        "AVG(bxp_hri) AS avg_hri, MIN(timestamp_us) AS first_ts, MAX(timestamp_us) AS last_ts "
        f"FROM readings WHERE {' AND '.join(clauses)}",
        params,
    ).fetchone()
    if not row or row["cnt"] < K_ANONYMITY_MIN:
        return None
    return {
        "geohash": geohash[:5],
        "count": row["cnt"],
        "hri": {"min": round(row["min_hri"], 1), "max": round(row["max_hri"], 1),
                "avg": round(row["avg_hri"], 1)},
        "firstTimestampUs": row["first_ts"],
        "lastTimestampUs": row["last_ts"],
        "kAnonymityMet": True,
        "kMinimum": K_ANONYMITY_MIN,
    }


def reading_count() -> int:
    return _conn().execute("SELECT COUNT(*) FROM readings WHERE deleted=0").fetchone()[0]


# ─── /nearby (SPEC.md section 7 Stage 6, section 8.2.1) ──────

# VALIDATED > UNVALIDATED > SUSPECT; INVALID is never returned.
QUALITY_RANK = {"INVALID": -1, "SUSPECT": 0, "UNVALIDATED": 1, "VALIDATED": 2}
_QUALITY_WEIGHT = {"VALIDATED": 1.15, "UNVALIDATED": 1.0, "SUSPECT": 0.6}


def get_nearby_readings(
    lat: float, lon: float,
    radius_m: int = 2000, max_age_s: int = 3600,
    agent: Optional[str] = None, min_quality: str = "UNVALIDATED",
    limit: int = 1, now_us: Optional[int] = None,
) -> list:
    """
    Relevance-ranked nearby lookup. The scoring blend (distance, freshness,
    quality multiplier) is deliberately an implementation detail (SPEC.md
    section 7 Stage 6); only the parameters and the "closer + fresher + better
    quality ranks higher, no single factor dominates" behaviour are contractual.

    Candidate cells are chosen by geo.precision_for_radius so the 3x3 geohash
    neighbourhood provably covers the whole search circle at this latitude.
    """
    limit, _ = _clamp_page(limit)
    now_us = now_us if now_us is not None else int(time.time() * 1_000_000)
    min_ts = now_us - int(max_age_s) * 1_000_000
    min_rank = max(QUALITY_RANK.get((min_quality or "UNVALIDATED").upper(), 1), 0)
    allowed = [q for q, rank in QUALITY_RANK.items() if rank >= min_rank]

    cells = geo.neighbors(geo.encode_geohash(lat, lon, geo.precision_for_radius(lat, radius_m)))
    cell_clauses, params = [], [min_ts]
    for cell in sorted(cells):
        clause, p = _prefix_clause("geohash", cell)
        cell_clauses.append(clause)
        params += p
    clauses = ["deleted=0", "timestamp_us >= ?", "latitude IS NOT NULL", "longitude IS NOT NULL",
               f"({' OR '.join(cell_clauses)})",
               f"quality_flag IN ({','.join('?' * len(allowed))})"]
    params += allowed
    if agent:
        clauses.append("instr(agent_ids, ?) > 0")
        params.append(f",{agent.upper()},")
    rows = _conn().execute(
        f"SELECT * FROM readings WHERE {' AND '.join(clauses)} "  # noqa: S608
        "ORDER BY timestamp_us DESC LIMIT ?",
        params + [MAX_NEARBY_CANDIDATES],
    ).fetchall()

    scored = []
    for row in rows:
        c = _row_to_reading(row)
        dist_m = geo.haversine_m(lat, lon, c["latitude"], c["longitude"])
        if dist_m > radius_m:
            continue
        age_s = max(0.0, (now_us - c["timestampUs"]) / 1_000_000)
        distance_score = max(0.0, 1 - dist_m / radius_m) if radius_m > 0 else 0.0
        freshness_score = max(0.0, 1 - age_s / max_age_s) if max_age_s > 0 else 0.0
        weight = _QUALITY_WEIGHT.get(c.get("qualityFlag"), 1.0)
        c["distanceM"] = round(dist_m, 1)
        c["relevanceScore"] = round((0.5 * distance_score + 0.5 * freshness_score) * weight, 4)
        scored.append(c)
    scored.sort(key=lambda c: c["relevanceScore"], reverse=True)
    return scored[:limit]


# ─── Federation pull (SPEC.md section 7 Stage 7, section 8.2.2) ─

def get_readings_since(cursor: int, limit: int = 500) -> tuple[list, int]:
    """
    Return (items, next_cursor): every change with seq > cursor, oldest first.
    A live reading is returned in full; a deleted one as a tombstone
    ({"readingId", "deleted": true, "deletionProof"}) so peers can erase it too.
    Resume from next_cursor. Ordering is by ingest sequence, so ties, late
    arrivals and far-future observation timestamps cannot skip or stall.
    """
    limit, _ = _clamp_page(limit)
    cursor = max(0, int(cursor))
    rows = _conn().execute(
        "SELECT * FROM readings WHERE seq > ? ORDER BY seq ASC LIMIT ?", (cursor, limit)
    ).fetchall()
    items = [
        {"readingId": r["reading_id"], "deleted": True, "deletionProof": r["deletion_proof"]}
        if r["deleted"] else _row_to_reading(r)
        for r in rows
    ]
    return items, (rows[-1]["seq"] if rows else cursor)


def _row_to_reading(row: sqlite3.Row) -> dict:
    record = {
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
        "agents":       _loads(row["agents_json"], []),
        "readings":     _loads(row["readings_json"], {}),
        "bxpHri":       row["bxp_hri"],
        "bxpHriLevel":  row["bxp_hri_level"],
        "quality":      _loads(row["quality_json"], {}),
        "qualityFlag":  row["quality_flag"],
        "payloadHash":  row["payload_hash"],
        "durationS":    row["duration_s"],
        "indoorOutdoor": row["indoor_outdoor"],
    }
    record.update(_loads(row["extra_json"], {}))
    return record


# ─── Devices ─────────────────────────────────────────────────

def register_device(device_uuid: str, token_hash: str,
                    label: Optional[str] = None,
                    owner_hash: Optional[str] = None) -> dict:
    """
    Register a NEW device. Raises DeviceExistsError if the UUID is taken or
    already appears on stored readings. (Re-registering an existing UUID would
    mint a fresh token for it, i.e. take the device over, and with it the right
    to delete its readings.)
    """
    with _tx() as conn:
        taken = conn.execute(
            "SELECT 1 FROM devices WHERE device_uuid=? "
            "UNION ALL SELECT 1 FROM readings WHERE device_uuid=? LIMIT 1",
            (device_uuid, device_uuid),
        ).fetchone()
        if taken:
            raise DeviceExistsError(device_uuid)
        try:
            conn.execute(
                "INSERT INTO devices (device_uuid, token_hash, label, owner_hash, "
                "registered_at, active) VALUES (?,?,?,?,?,1)",
                (device_uuid, token_hash, label, owner_hash, int(time.time())),
            )
        except sqlite3.IntegrityError as e:
            raise DeviceExistsError(device_uuid) from e
    return get_device(device_uuid)


def get_device(device_uuid: str) -> Optional[dict]:
    row = _conn().execute("SELECT * FROM devices WHERE device_uuid=?", (device_uuid,)).fetchone()
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


def is_registered_device(device_uuid: str) -> bool:
    return _conn().execute(
        "SELECT 1 FROM devices WHERE device_uuid=?", (device_uuid,)
    ).fetchone() is not None


def validate_token(token: str) -> Optional[str]:
    """Returns device_uuid if the token is valid and its device active, else None."""
    token_hash = "sha256:" + hashlib.sha256(token.encode()).hexdigest()
    row = _conn().execute(
        "SELECT device_uuid FROM devices WHERE token_hash=? AND active=1", (token_hash,)
    ).fetchone()
    return row["device_uuid"] if row else None


def bump_device_seen(device_uuid: str, ts_us: int, count: int = 1) -> None:
    with _tx() as conn:
        conn.execute(
            "UPDATE devices SET last_seen_us=MAX(COALESCE(last_seen_us, 0), ?), "
            "reading_count=reading_count+? WHERE device_uuid=?",
            (ts_us, count, device_uuid),
        )


# ─── Community reports ───────────────────────────────────────

def insert_report(report: dict) -> None:
    with _tx() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO community_reports
               (report_id, geohash, latitude, longitude, timestamp_iso, timestamp_us,
                report_type, description, severity, submitter_hash, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (report["reportId"], report.get("geohash", ""), report.get("latitude"),
             report.get("longitude"), report.get("timestamp", ""), report.get("timestampUs", 0),
             report.get("reportType", "observation"), report.get("description"),
             report.get("severity"), report.get("submitterHash"), int(time.time())),
        )


def query_reports(geohash: Optional[str] = None, limit: int = 50) -> list:
    limit, _ = _clamp_page(limit)
    if geohash:
        clause, params = _prefix_clause("geohash", geohash)
        rows = _conn().execute(
            f"SELECT * FROM community_reports WHERE {clause} "  # noqa: S608
            "ORDER BY timestamp_us DESC LIMIT ?", params + [limit]).fetchall()
    else:
        rows = _conn().execute(
            "SELECT * FROM community_reports ORDER BY timestamp_us DESC LIMIT ?",
            (limit,)).fetchall()
    return [dict(r) for r in rows]


# ─── Federated nodes ─────────────────────────────────────────

def upsert_node(node_id: str, base_url: str, bxp_version: str = "2.0",
                node_type: str = "reference", reading_count: int = 0) -> None:
    """
    Record a node announcement. A node_id may refresh its own entry but may not
    change its base_url (that would let anyone redirect an existing node's
    listing); a base_url already listed under another node_id is refused.
    """
    with _tx() as conn:
        existing = conn.execute(
            "SELECT base_url FROM federated_nodes WHERE node_id=?", (node_id,)).fetchone()
        if existing and existing["base_url"] != base_url:
            raise NodeRegistryError("node_id is already registered with a different baseUrl")
        if not existing:
            count = conn.execute("SELECT COUNT(*) FROM federated_nodes").fetchone()[0]
            if count >= MAX_REGISTERED_NODES:
                raise NodeRegistryError("node registry is full")
            if conn.execute("SELECT 1 FROM federated_nodes WHERE base_url=?",
                            (base_url,)).fetchone():
                raise NodeRegistryError("baseUrl is already registered by another node")
        conn.execute(
            """INSERT INTO federated_nodes
               (node_id, base_url, last_seen, bxp_version, node_type, reading_count, active)
               VALUES (?,?,?,?,?,?,1)
               ON CONFLICT(node_id) DO UPDATE SET
                 last_seen=excluded.last_seen, bxp_version=excluded.bxp_version,
                 node_type=excluded.node_type, reading_count=excluded.reading_count, active=1""",
            (node_id, base_url, int(time.time()), bxp_version, node_type, reading_count),
        )


def get_nodes(active_only: bool = True) -> list:
    query = "SELECT * FROM federated_nodes"
    if active_only:
        query += " WHERE active=1"
    query += " ORDER BY last_seen DESC LIMIT ?"
    return [dict(r) for r in _conn().execute(query, (MAX_REGISTERED_NODES,)).fetchall()]
