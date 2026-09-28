/**
 * BXP Binary Container Format (SPEC.md §5.1-5.2, §5.7-5.9)
 * Breathe Exposure Protocol
 *
 * TypeScript counterpart to sdk/python/bxp_binary.py. The two MUST stay
 * byte-for-byte compatible -- that's what conformance/verify_typescript.mjs
 * checks against the shared golden vectors in conformance/vectors/.
 *
 * Header layout (big-endian, 32 bytes total) -- see bxp_binary.py for the
 * full field-by-field description; it is not repeated here to avoid the
 * two comments drifting out of sync. SPEC.md is the source of truth.
 *
 * Works in Node.js (18+, for Buffer/crypto) and browsers/edge runtimes
 * that provide CompressionStream/DecompressionStream ("gzip") -- see
 * gzipCompress/gzipDecompress below for the environment split.
 */

// ─── Constants ────────────────────────────────────────────────

export const MAGIC = 0x42585000; // "BXP\0"

/** Highest major version this decoder understands (SPEC.md §5.8). */
export const SUPPORTED_MAJOR = 2;

export const HEADER_SIZE = 32;

export const FILE_TYPES: Record<string, number> = {
  reading: 0x01,
  aggregate: 0x02,
  agent: 0x03,
  device: 0x04,
  alert: 0x05,
  meta: 0x06,
};

const FILE_TYPES_REV: Record<number, string> = Object.fromEntries(
  Object.entries(FILE_TYPES).map(([k, v]) => [v, k])
);

export const FLAG_COMPRESSED = 1 << 0;
export const FLAG_ENCRYPTED = 1 << 1;
export const FLAG_SIGNED = 1 << 2;
export const FLAG_DRAFT = 1 << 3;

export class BXPBinaryError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'BXPBinaryError';
  }
}

export interface BxpBinaryHeader {
  majorVersion: number;
  minorVersion: number;
  fileType: string | number;
  flags: {
    compressed: boolean;
    encrypted: boolean;
    signed: boolean;
    draft: boolean;
  };
  timestampUs: bigint;
  payloadLength: number;
}

export interface DecodedBxpBinary {
  record: Record<string, unknown>;
  header: BxpBinaryHeader;
  headerChecksumOk: boolean;
  payloadChecksumOk: boolean;
  majorVersionSupported: boolean;
}

// ─── CRC32 (no external dependency, mirrors zlib.crc32 exactly) ─

const CRC_TABLE = (() => {
  const table = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) {
      c = c & 1 ? (0xedb88320 ^ (c >>> 1)) : c >>> 1;
    }
    table[n] = c >>> 0;
  }
  return table;
})();

export function crc32(buf: Uint8Array): number {
  let crc = 0xffffffff;
  for (let i = 0; i < buf.length; i++) {
    crc = CRC_TABLE[(crc ^ buf[i]) & 0xff] ^ (crc >>> 8);
  }
  return (crc ^ 0xffffffff) >>> 0;
}

// ─── gzip (Node Buffer path; browsers use CompressionStream) ────

async function gzipCompress(data: Uint8Array): Promise<Uint8Array> {
  if (typeof (globalThis as any).CompressionStream === 'undefined') {
    throw new Error(
      'CompressionStream is not available in this runtime; compressed .bxp ' +
      'encoding requires it (Node.js 18+, modern browsers, Deno, Bun, ' +
      'Cloudflare Workers all provide it).'
    );
  }
  const cs = new (globalThis as any).CompressionStream('gzip');
  const writer = cs.writable.getWriter();
  writer.write(data);
  writer.close();
  const chunks: Uint8Array[] = [];
  const reader = cs.readable.getReader();
  // eslint-disable-next-line no-constant-condition
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    chunks.push(value);
  }
  return concatBytes(chunks);
}

/** Max size a compressed payload may inflate to (decompression-bomb guard). */
export const MAX_DECOMPRESSED_BYTES = 16 * 1024 * 1024;

async function gzipDecompress(data: Uint8Array): Promise<Uint8Array> {
  if (typeof (globalThis as any).DecompressionStream === 'undefined') {
    throw new Error(
      'DecompressionStream is not available in this runtime; decoding a ' +
      'compressed .bxp file requires it (Node.js 18+, modern browsers, ' +
      'Deno, Bun, Cloudflare Workers all provide it).'
    );
  }
  const ds = new (globalThis as any).DecompressionStream('gzip');
  const writer = ds.writable.getWriter();
  // If we abort early (size limit / corrupt stream) these reject with an
  // AbortError; unhandled, that would crash a Node process.
  writer.write(data).catch(() => {});
  writer.close().catch(() => {});
  const chunks: Uint8Array[] = [];
  const reader = ds.readable.getReader();
  let total = 0;
  // eslint-disable-next-line no-constant-condition
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    total += value.length;
    if (total > MAX_DECOMPRESSED_BYTES) {
      await reader.cancel();
      throw new BXPBinaryError(
        `Decompressed payload exceeds the ${MAX_DECOMPRESSED_BYTES}-byte limit ` +
        '(possible decompression bomb)'
      );
    }
    chunks.push(value);
  }
  return concatBytes(chunks);
}

function concatBytes(chunks: Uint8Array[]): Uint8Array {
  const total = chunks.reduce((n, c) => n + c.length, 0);
  const out = new Uint8Array(total);
  let offset = 0;
  for (const c of chunks) {
    out.set(c, offset);
    offset += c.length;
  }
  return out;
}

// ─── Canonical JSON (sorted keys, tight separators) ─────────────

/**
 * Matches Python's json.dumps(record, sort_keys=True, separators=(",", ":")).
 * This exact byte sequence is what payloadHash and the binary payload are
 * both computed over (SPEC.md §5.5), so it MUST match the Python
 * implementation's canonicalization precisely.
 */
export function canonicalJson(value: unknown): string {
  if (value === null || typeof value !== 'object') {
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    return '[' + value.map(canonicalJson).join(',') + ']';
  }
  const keys = Object.keys(value as Record<string, unknown>).sort();
  const parts = keys.map(
    (k) => JSON.stringify(k) + ':' + canonicalJson((value as Record<string, unknown>)[k])
  );
  return '{' + parts.join(',') + '}';
}

function versionTuple(bxpVersion: string | undefined): [number, number] {
  const parts = String(bxpVersion ?? '2.0').split('.');
  const major = parts[0] && /^\d+$/.test(parts[0]) ? parseInt(parts[0], 10) : 2;
  const minor = parts[1] && /^\d+$/.test(parts[1]) ? parseInt(parts[1], 10) : 0;
  return [major, minor];
}

// ─── Header pack/unpack (big-endian, matches Python's struct format) ────

function packHeader(
  major: number, minor: number, fileTypeCode: number, flags: number,
  timestampUs: bigint, payloadLength: number
): Uint8Array {
  const buf = new ArrayBuffer(24); // HEADER_STRUCT: >IHHBBHqI
  const view = new DataView(buf);
  view.setUint32(0, MAGIC, false);
  view.setUint16(4, major, false);
  view.setUint16(6, minor, false);
  view.setUint8(8, fileTypeCode);
  view.setUint8(9, flags);
  view.setUint16(10, 0, false); // reserved
  view.setBigInt64(12, timestampUs, false);
  view.setUint32(20, payloadLength, false);
  return new Uint8Array(buf);
}

function unpackHeader(bytes: Uint8Array) {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  return {
    magic: view.getUint32(0, false),
    major: view.getUint16(4, false),
    minor: view.getUint16(6, false),
    fileTypeCode: view.getUint8(8),
    flags: view.getUint8(9),
    reserved: view.getUint16(10, false),
    timestampUs: view.getBigInt64(12, false),
    payloadLength: view.getUint32(20, false),
  };
}

// ─── Public API ──────────────────────────────────────────────

export interface EncodeOptions {
  fileType?: keyof typeof FILE_TYPES | string;
  compress?: boolean;
  encrypt?: boolean;
  signed?: boolean;
  draft?: boolean;
}

/**
 * Encode a BXP record into the binary `.bxp` container format
 * (SPEC.md §5.2). Mirrors bxp_binary.py::encode_bxp_binary exactly.
 */
export async function encodeBxpBinary(
  record: Record<string, unknown>,
  options: EncodeOptions = {}
): Promise<Uint8Array> {
  const { fileType = 'reading', compress = false, encrypt = false, signed = false, draft = false } = options;

  if (encrypt) {
    throw new Error(
      'BXP binary encryption (flag bit1) is specified but its cipher/key-exchange ' +
      'is not yet defined in SPEC.md (§5.10); encode an unencrypted container and ' +
      'encrypt the file at rest instead.'
    );
  }
  if (!(fileType in FILE_TYPES)) {
    throw new RangeError(`Unknown file_type ${JSON.stringify(fileType)}; expected one of ${Object.keys(FILE_TYPES).sort()}`);
  }

  const [major, minor] = versionTuple(record.bxpVersion as string | undefined);

  const payloadJson = new TextEncoder().encode(canonicalJson(record));

  let flags = 0;
  let payload: Uint8Array;
  if (compress) {
    payload = await gzipCompress(payloadJson);
    flags |= FLAG_COMPRESSED;
  } else {
    payload = payloadJson;
  }
  if (signed) flags |= FLAG_SIGNED;
  if (draft) flags |= FLAG_DRAFT;

  const tsUs = BigInt(Math.trunc(Number(record.timestampUs ?? 0)));

  const headerBody = packHeader(major, minor, FILE_TYPES[fileType], flags, tsUs, payload.length);
  const headerChecksum = crc32(headerBody);
  const payloadChecksum = crc32(payload);

  const checksums = new ArrayBuffer(8);
  const csView = new DataView(checksums);
  csView.setUint32(0, headerChecksum, false);
  csView.setUint32(4, payloadChecksum, false);

  const out = new Uint8Array(headerBody.length + 8 + payload.length);
  out.set(headerBody, 0);
  out.set(new Uint8Array(checksums), headerBody.length);
  out.set(payload, headerBody.length + 8);
  return out;
}

export interface DecodeOptions {
  verify?: boolean;
  supportedMajor?: number;
}

/**
 * Decode a binary `.bxp` container back into a record plus header
 * metadata. Mirrors bxp_binary.py::decode_bxp_binary exactly, including
 * the SPEC.md §5.8 major-version rejection policy.
 */
export async function decodeBxpBinary(
  raw: Uint8Array,
  options: DecodeOptions = {}
): Promise<DecodedBxpBinary> {
  const { verify = true, supportedMajor = SUPPORTED_MAJOR } = options;

  if (raw.length < HEADER_SIZE) {
    throw new BXPBinaryError(
      `File too short to be a .bxp binary container: ${raw.length} bytes (need at least ${HEADER_SIZE})`
    );
  }

  const headerBody = raw.subarray(0, 24);
  const checksumsRaw = raw.subarray(24, HEADER_SIZE);
  const payload = raw.subarray(HEADER_SIZE);

  const { magic, major, minor, fileTypeCode, flags, timestampUs, payloadLength } = unpackHeader(headerBody);
  const csView = new DataView(checksumsRaw.buffer, checksumsRaw.byteOffset, checksumsRaw.byteLength);
  const headerChecksum = csView.getUint32(0, false);
  const payloadChecksum = csView.getUint32(4, false);

  if (magic !== MAGIC) {
    throw new BXPBinaryError(
      `Bad magic number: 0x${magic.toString(16).toUpperCase()} (expected 0x${MAGIC.toString(16).toUpperCase()}) — not a .bxp binary file`
    );
  }

  const majorVersionSupported = major === supportedMajor;
  if (verify && !majorVersionSupported) {
    throw new BXPBinaryError(
      `Unsupported major version ${major} (this decoder supports major version ${supportedMajor}) — refusing to guess at payload structure per SPEC.md §5.8`
    );
  }

  const computedHeaderChecksum = crc32(headerBody);
  const headerChecksumOk = computedHeaderChecksum === headerChecksum;
  if (verify && !headerChecksumOk) {
    throw new BXPBinaryError(
      `Header checksum mismatch: file claims 0x${headerChecksum.toString(16)}, computed 0x${computedHeaderChecksum.toString(16)} — header may be corrupt`
    );
  }

  if (payload.length !== payloadLength && verify) {
    throw new BXPBinaryError(
      `Payload length mismatch: header claims ${payloadLength} bytes, found ${payload.length}`
    );
  }

  const computedPayloadChecksum = crc32(payload);
  const payloadChecksumOk = computedPayloadChecksum === payloadChecksum;
  if (verify && !payloadChecksumOk) {
    throw new BXPBinaryError(
      `Payload checksum mismatch: file claims 0x${payloadChecksum.toString(16)}, computed 0x${computedPayloadChecksum.toString(16)} — payload may be corrupt or truncated`
    );
  }

  let payloadJsonBytes = payload;
  if (flags & FLAG_COMPRESSED) {
    try {
      payloadJsonBytes = await gzipDecompress(payload);
    } catch (e) {
      throw new BXPBinaryError(`Failed to gzip-decompress payload: ${(e as Error).message}`);
    }
  }

  let record: Record<string, unknown>;
  try {
    record = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(payloadJsonBytes));
  } catch (e) {
    throw new BXPBinaryError(`Payload is not valid JSON: ${(e as Error).message}`);
  }

  return {
    record,
    header: {
      majorVersion: major,
      minorVersion: minor,
      fileType: FILE_TYPES_REV[fileTypeCode] ?? fileTypeCode,
      flags: {
        compressed: !!(flags & FLAG_COMPRESSED),
        encrypted: !!(flags & FLAG_ENCRYPTED),
        signed: !!(flags & FLAG_SIGNED),
        draft: !!(flags & FLAG_DRAFT),
      },
      timestampUs,
      payloadLength,
    },
    headerChecksumOk,
    payloadChecksumOk,
    majorVersionSupported,
  };
}
