"""
BXP Binary Container Format (spec §5.1–5.2)
Breathe Exposure Protocol

Implements the native binary `.bxp` container: a 32-byte fixed header
followed by a JSON payload (optionally gzip-compressed). This is the
"compact, efficient, designed for devices" counterpart to `.bxp.json`
described in SPEC.md section 5.1. Per spec, both representations MUST
be losslessly interconvertible — that round trip is what this module
and its tests guarantee.

Header layout (big-endian, 32 bytes total):

    Offset  Len  Field
    0x00    4    Magic Number      0x42585000  ("BXP\\0")
    0x04    2    Major Version     uint16
    0x06    2    Minor Version     uint16
    0x08    1    File Type         0x01=reading 0x02=aggregate 0x03=agent
                                    0x04=device  0x05=alert     0x06=meta
    0x09    1    Flags             bit0=compressed bit1=encrypted
                                    bit2=signed      bit3=draft
    0x0A    2    Reserved          0x0000
    0x0C    8    Timestamp         Unix epoch microseconds, int64
    0x14    4    Payload Length    uint32, size of payload AS STORED
                                    (i.e. after compression, if any)
    0x18    4    Header Checksum   CRC32 of bytes 0x00-0x17
    0x1C    4    Payload Checksum  CRC32 of the stored payload bytes

Encryption (flag bit1) is specified but its cipher/key-exchange is not
yet pinned down in SPEC.md — encode_bxp_binary raises NotImplementedError
if asked to encrypt, rather than silently producing a non-interoperable
file. Everything else (compression, signing flag passthrough, checksums,
round trip) is fully implemented.

Usage:
    from bxp_binary import encode_bxp_binary, decode_bxp_binary

    raw = encode_bxp_binary(record, file_type="reading", compress=True)
    Path("reading.bxp").write_bytes(raw)

    decoded = decode_bxp_binary(Path("reading.bxp").read_bytes())
    record = decoded["record"]
"""

import gzip
import json
import struct
import zlib
from typing import Optional

MAGIC = 0x42585000  # "BXP\0"

HEADER_STRUCT = struct.Struct(">IHHBBHqI")  # bytes 0x00-0x17 (24 bytes)
CHECKSUM_STRUCT = struct.Struct(">II")      # bytes 0x18-0x1F (8 bytes)
HEADER_SIZE = HEADER_STRUCT.size + CHECKSUM_STRUCT.size  # 32

FILE_TYPES = {
    "reading":   0x01,
    "aggregate": 0x02,
    "agent":     0x03,
    "device":    0x04,
    "alert":     0x05,
    "meta":      0x06,
}
FILE_TYPES_REV = {v: k for k, v in FILE_TYPES.items()}

FLAG_COMPRESSED = 1 << 0
FLAG_ENCRYPTED  = 1 << 1
FLAG_SIGNED     = 1 << 2
FLAG_DRAFT      = 1 << 3


class BXPBinaryError(ValueError):
    """Raised when a .bxp binary file fails to parse or verify."""


def _version_tuple(bxp_version: str) -> tuple:
    parts = str(bxp_version).split(".")
    major = int(parts[0]) if len(parts) > 0 and parts[0].isdigit() else 2
    minor = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
    return major, minor


def encode_bxp_binary(
    record: dict,
    file_type: str = "reading",
    compress: bool = False,
    encrypt: bool = False,
    signed: bool = False,
    draft: bool = False,
) -> bytes:
    """
    Encode a BXP record dict into the binary `.bxp` container format
    (spec §5.2). The payload is the record's canonical JSON serialization
    (sorted keys, tight separators — the same canonicalization write_bxp
    uses for payloadHash), optionally gzip-compressed.

    Args:
        record:    A BXP reading/aggregate/agent/device/alert/meta record,
                   e.g. as returned by write_bxp() / bxp_sdk record dicts.
        file_type: One of FILE_TYPES keys ("reading", "aggregate", "agent",
                   "device", "alert", "meta"). Defaults to "reading".
        compress:  If True, gzip-compress the JSON payload and set flag bit0.
        encrypt:   Not yet implemented (spec's encryption scheme is not
                   pinned down) — raises NotImplementedError if True.
        signed:    Sets flag bit2 to advertise a signature is present in
                   the payload's own "signature" field. Does not itself
                   compute a signature (that's the SDK/device's job).
        draft:     Sets flag bit3 (draft/unfinalized record).

    Returns:
        Raw bytes: 32-byte header + payload.
    """
    if encrypt:
        raise NotImplementedError(
            "BXP binary encryption (flag bit1) is specified but its "
            "cipher/key-exchange is not yet defined in SPEC.md; encode "
            "an unencrypted container and encrypt the file at rest instead."
        )

    if file_type not in FILE_TYPES:
        raise ValueError(
            f"Unknown file_type {file_type!r}; expected one of "
            f"{sorted(FILE_TYPES)}"
        )

    major, minor = _version_tuple(record.get("bxpVersion", "2.0"))

    payload_json = json.dumps(
        record, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")

    flags = 0
    if compress:
        payload = gzip.compress(payload_json, mtime=0)
        flags |= FLAG_COMPRESSED
    else:
        payload = payload_json
    if signed:
        flags |= FLAG_SIGNED
    if draft:
        flags |= FLAG_DRAFT

    ts_us = int(record.get("timestampUs") or 0)

    header_body = HEADER_STRUCT.pack(
        MAGIC, major, minor, FILE_TYPES[file_type], flags, 0x0000,
        ts_us, len(payload)
    )
    header_checksum = zlib.crc32(header_body) & 0xFFFFFFFF
    payload_checksum = zlib.crc32(payload) & 0xFFFFFFFF
    checksums = CHECKSUM_STRUCT.pack(header_checksum, payload_checksum)

    return header_body + checksums + payload


def decode_bxp_binary(raw: bytes, verify: bool = True) -> dict:
    """
    Decode a binary `.bxp` container back into a BXP record dict plus
    header metadata.

    Args:
        raw:    Full file contents (header + payload).
        verify: If True (default), raise BXPBinaryError on magic number,
                length, or checksum mismatch instead of returning a
                result with integrity flags set to False.

    Returns:
        {
          "record": <decoded dict>,
          "header": {
              "majorVersion", "minorVersion", "fileType", "flags",
              "timestampUs", "payloadLength",
          },
          "headerChecksumOk": bool,
          "payloadChecksumOk": bool,
        }
    """
    if len(raw) < HEADER_SIZE:
        raise BXPBinaryError(
            f"File too short to be a .bxp binary container: "
            f"{len(raw)} bytes (need at least {HEADER_SIZE})"
        )

    header_body = raw[:HEADER_STRUCT.size]
    checksums_raw = raw[HEADER_STRUCT.size:HEADER_SIZE]
    payload = raw[HEADER_SIZE:]

    magic, major, minor, file_type_code, flags, reserved, ts_us, payload_len = (
        HEADER_STRUCT.unpack(header_body)
    )
    header_checksum, payload_checksum = CHECKSUM_STRUCT.unpack(checksums_raw)

    if magic != MAGIC:
        raise BXPBinaryError(
            f"Bad magic number: 0x{magic:08X} (expected 0x{MAGIC:08X}) — "
            "not a .bxp binary file"
        )

    computed_header_checksum = zlib.crc32(header_body) & 0xFFFFFFFF
    header_checksum_ok = computed_header_checksum == header_checksum
    if verify and not header_checksum_ok:
        raise BXPBinaryError(
            f"Header checksum mismatch: file claims 0x{header_checksum:08X}, "
            f"computed 0x{computed_header_checksum:08X} — header may be corrupt"
        )

    if len(payload) != payload_len:
        msg = (
            f"Payload length mismatch: header claims {payload_len} bytes, "
            f"found {len(payload)}"
        )
        if verify:
            raise BXPBinaryError(msg)

    computed_payload_checksum = zlib.crc32(payload) & 0xFFFFFFFF
    payload_checksum_ok = computed_payload_checksum == payload_checksum
    if verify and not payload_checksum_ok:
        raise BXPBinaryError(
            f"Payload checksum mismatch: file claims 0x{payload_checksum:08X}, "
            f"computed 0x{computed_payload_checksum:08X} — payload may be "
            "corrupt or truncated"
        )

    payload_json = payload
    if flags & FLAG_COMPRESSED:
        try:
            payload_json = gzip.decompress(payload)
        except OSError as e:
            raise BXPBinaryError(f"Failed to gzip-decompress payload: {e}")

    try:
        record = json.loads(payload_json.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise BXPBinaryError(f"Payload is not valid JSON: {e}")

    return {
        "record": record,
        "header": {
            "majorVersion":  major,
            "minorVersion":  minor,
            "fileType":      FILE_TYPES_REV.get(file_type_code, file_type_code),
            "flags": {
                "compressed": bool(flags & FLAG_COMPRESSED),
                "encrypted":  bool(flags & FLAG_ENCRYPTED),
                "signed":     bool(flags & FLAG_SIGNED),
                "draft":      bool(flags & FLAG_DRAFT),
            },
            "timestampUs":   ts_us,
            "payloadLength": payload_len,
        },
        "headerChecksumOk":  header_checksum_ok,
        "payloadChecksumOk": payload_checksum_ok,
    }


def bxp_json_to_binary(
    json_path,
    binary_path,
    file_type: str = "reading",
    compress: bool = False,
) -> bytes:
    """Convert a .bxp.json file on disk to a binary .bxp file. Returns the raw bytes written."""
    from pathlib import Path
    record = json.loads(Path(json_path).read_text(encoding="utf-8"))
    raw = encode_bxp_binary(record, file_type=file_type, compress=compress)
    Path(binary_path).write_bytes(raw)
    return raw


def bxp_binary_to_json(binary_path, json_path) -> dict:
    """Convert a binary .bxp file on disk to a .bxp.json file. Returns the decoded record."""
    from pathlib import Path
    raw = Path(binary_path).read_bytes()
    decoded = decode_bxp_binary(raw)
    Path(json_path).write_text(
        json.dumps(decoded["record"], indent=2, default=str), encoding="utf-8"
    )
    return decoded["record"]
