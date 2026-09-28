/**
 * Tests for bxp-binary.ts, mirroring sdk/python/tests/test_bxp_binary.py's
 * coverage so the two implementations are checked against the same
 * expectations (in addition to conformance/verify_typescript.mjs, which
 * checks both against the same golden byte vectors).
 *
 * Zero dependencies deliberately: uses Node's built-in test runner and
 * assert module, and Node's built-in TypeScript support, so these run
 * with nothing but Node itself:
 *
 *   node --experimental-strip-types --test tests/bxp-binary.test.ts   (Node 22.6-22.17)
 *   node --test tests/bxp-binary.test.ts                              (Node 22.18+/23.6+, type stripping on by default)
 *
 * (The `npm test` / jest path in package.json remains the toolchain for
 * the rest of the SDK once `npm install` has network access; this file
 * exists so binary-format correctness can be verified even without it.)
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import {
  MAGIC, HEADER_SIZE, FILE_TYPES, SUPPORTED_MAJOR,
  FLAG_COMPRESSED, FLAG_ENCRYPTED, FLAG_SIGNED, FLAG_DRAFT,
  encodeBxpBinary, decodeBxpBinary, BXPBinaryError, crc32,
} from '../bxp-binary.ts';

const SAMPLE_RECORD = {
  bxpVersion: '2.0',
  deviceUuid: '550e8400-e29b-41d4-a716-446655440000',
  geohash: 's1v0g',
  timestampUs: 1710000000000000,
  agents: [{ agentId: 'PM2_5', value: 47.3, unit: 'ug/m3' }],
  quality: { flag: 'UNVALIDATED' },
};

test('magic number matches spec', async () => {
  assert.equal(MAGIC, 0x42585000);
});

test('header is 32 bytes', async () => {
  const raw = await encodeBxpBinary(SAMPLE_RECORD);
  assert.ok(raw.length >= HEADER_SIZE);
});

test('round trip uncompressed is lossless', async () => {
  const raw = await encodeBxpBinary(SAMPLE_RECORD, { fileType: 'reading' });
  const decoded = await decodeBxpBinary(raw);
  assert.deepEqual(decoded.record, SAMPLE_RECORD);
  assert.equal(decoded.headerChecksumOk, true);
  assert.equal(decoded.payloadChecksumOk, true);
});

test('round trip compressed is lossless', async () => {
  const raw = await encodeBxpBinary(SAMPLE_RECORD, { fileType: 'reading', compress: true });
  const decoded = await decodeBxpBinary(raw);
  assert.deepEqual(decoded.record, SAMPLE_RECORD);
  assert.equal(decoded.header.flags.compressed, true);
});

test('all file type codes match spec table', async () => {
  const expected: Record<string, number> = {
    reading: 1, aggregate: 2, agent: 3, device: 4, alert: 5, meta: 6,
  };
  for (const [fileType, code] of Object.entries(expected)) {
    const raw = await encodeBxpBinary(SAMPLE_RECORD, { fileType });
    assert.equal(raw[8], code, `${fileType} should encode as 0x0${code}`);
  }
});

test('unknown file type is rejected', async () => {
  await assert.rejects(
    () => encodeBxpBinary(SAMPLE_RECORD, { fileType: 'bogus' }),
    RangeError
  );
});

test('encryption is not implemented', async () => {
  await assert.rejects(
    () => encodeBxpBinary(SAMPLE_RECORD, { encrypt: true })
  );
});

test('signed and draft flags round-trip', async () => {
  const raw = await encodeBxpBinary(SAMPLE_RECORD, { signed: true, draft: true });
  const decoded = await decodeBxpBinary(raw);
  assert.equal(decoded.header.flags.signed, true);
  assert.equal(decoded.header.flags.draft, true);
  assert.equal(decoded.header.flags.compressed, false);
  assert.equal(decoded.header.flags.encrypted, false);
});

test('bad magic number is rejected', async () => {
  const raw = await encodeBxpBinary(SAMPLE_RECORD);
  const corrupted = new Uint8Array(raw);
  corrupted[0] ^= 0xff;
  await assert.rejects(() => decodeBxpBinary(corrupted), BXPBinaryError);
});

test('too-short file is rejected', async () => {
  await assert.rejects(() => decodeBxpBinary(new Uint8Array(10)), BXPBinaryError);
});

test('tampered payload byte is detected', async () => {
  const raw = await encodeBxpBinary(SAMPLE_RECORD);
  const corrupted = new Uint8Array(raw);
  corrupted[HEADER_SIZE + 2] ^= 0xff;
  await assert.rejects(() => decodeBxpBinary(corrupted), BXPBinaryError);
});

test('tampered payload is reported not raised when verify=false', async () => {
  const raw = await encodeBxpBinary(SAMPLE_RECORD);
  const corrupted = new Uint8Array(raw);
  // Flip an ASCII digit inside the JSON payload so it stays syntactically
  // valid JSON but no longer matches the stored checksum (mirrors the
  // Python test's approach -- flipping an arbitrary byte can break JSON
  // syntax itself, which is a different, always-fatal error path).
  const text = new TextDecoder().decode(corrupted.subarray(HEADER_SIZE));
  const digitIndex = text.indexOf('4');
  corrupted[HEADER_SIZE + digitIndex] = '9'.charCodeAt(0);
  const decoded = await decodeBxpBinary(corrupted, { verify: false });
  assert.equal(decoded.payloadChecksumOk, false);
});

test('unsupported major version is rejected when verify=true', async () => {
  const record = { ...SAMPLE_RECORD, bxpVersion: '99.0' };
  const raw = await encodeBxpBinary(record);
  await assert.rejects(() => decodeBxpBinary(raw, { verify: true }), BXPBinaryError);
});

test('unsupported major version is reported not raised when verify=false', async () => {
  const record = { ...SAMPLE_RECORD, bxpVersion: '99.0' };
  const raw = await encodeBxpBinary(record);
  const decoded = await decodeBxpBinary(raw, { verify: false });
  assert.equal(decoded.majorVersionSupported, false);
});

test('higher minor version, same major, is accepted', async () => {
  const record = { ...SAMPLE_RECORD, bxpVersion: '2.99' };
  const raw = await encodeBxpBinary(record);
  const decoded = await decodeBxpBinary(raw, { verify: true });
  assert.equal(decoded.majorVersionSupported, true);
  assert.equal(decoded.header.minorVersion, 99);
});

test('unknown top-level fields survive a decode/encode round trip (SPEC.md §5.7)', async () => {
  const record = { ...SAMPLE_RECORD, ext: { 'org.example.mycompany': { batch: 'B-1' } } };
  const raw = await encodeBxpBinary(record);
  const decoded = await decodeBxpBinary(raw);
  assert.deepEqual(decoded.record.ext, { 'org.example.mycompany': { batch: 'B-1' } });
});

test('crc32 matches known test vector', async () => {
  // "123456789" -> 0xCBF43926 is the standard CRC-32 check value.
  const bytes = new TextEncoder().encode('123456789');
  assert.equal(crc32(bytes), 0xcbf43926);
});

test('flag bit values match spec', async () => {
  assert.equal(FLAG_COMPRESSED, 1);
  assert.equal(FLAG_ENCRYPTED, 2);
  assert.equal(FLAG_SIGNED, 4);
  assert.equal(FLAG_DRAFT, 8);
});

test('supported major version constant matches Python default', async () => {
  assert.equal(SUPPORTED_MAJOR, 2);
});

// ── Decompression-bomb hardening ────────────────────────────────

test('decompression bomb is rejected, not inflated', async () => {
  const { gzipSync } = await import('node:zlib');
  const { crc32: crc } = await import('../bxp-binary.ts');
  const { MAX_DECOMPRESSED_BYTES: LIMIT } = await import('../bxp-binary.ts');
  const bomb = gzipSync(Buffer.alloc(LIMIT * 4), { level: 9 }); // ~64 MB inflated
  assert.ok(bomb.length < 1024 * 1024);

  const header = new Uint8Array(24);
  const dv = new DataView(header.buffer);
  dv.setUint32(0, 0x42585000);
  dv.setUint16(4, 2);
  dv.setUint8(8, 0x01);
  dv.setUint8(9, 0x01); // compressed
  dv.setUint32(20, bomb.length);
  const out = new Uint8Array(32 + bomb.length);
  out.set(header, 0);
  const cdv = new DataView(out.buffer);
  cdv.setUint32(24, crc(header));
  cdv.setUint32(28, crc(new Uint8Array(bomb)));
  out.set(bomb, 32);

  const before = process.memoryUsage().rss;
  await assert.rejects(() => decodeBxpBinary(out), /exceeds|bomb/i);
  const grownMb = (process.memoryUsage().rss - before) / 1e6;
  assert.ok(grownMb < 200, `memory grew by ${grownMb.toFixed(0)} MB`);
});
