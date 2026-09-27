#!/usr/bin/env node
/**
 * Verifies sdk/typescript/bxp-binary.ts against conformance/manifest.json --
 * the TypeScript counterpart to verify_python.py, checked against the
 * exact same golden vector files.
 *
 * Run with (Node 22.6+, which has TypeScript type-stripping built in):
 *   node conformance/verify_typescript.mjs
 *
 * On older Node, run via tsx/ts-node instead:
 *   npx tsx conformance/verify_typescript.mjs
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const here = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(here, '..');

const { decodeBxpBinary, BXPBinaryError } = await import(
  path.join(repoRoot, 'sdk', 'typescript', 'bxp-binary.ts')
);

const manifest = JSON.parse(readFileSync(path.join(here, 'manifest.json'), 'utf8'));

function deepEqual(a, b) {
  return JSON.stringify(sortedKeys(a)) === JSON.stringify(sortedKeys(b));
}
function sortedKeys(v) {
  if (v === null || typeof v !== 'object') return v;
  if (Array.isArray(v)) return v.map(sortedKeys);
  const out = {};
  for (const k of Object.keys(v).sort()) out[k] = sortedKeys(v[k]);
  return out;
}

async function run() {
  let passed = 0;
  let failed = 0;

  for (const v of manifest.vectors) {
    const filePath = path.join(here, 'vectors', v.file);
    const raw = new Uint8Array(readFileSync(filePath));
    const name = v.file;
    try {
      if (v.expectValid) {
        const decoded = await decodeBxpBinary(raw, { verify: true });
        if (!decoded.headerChecksumOk) throw new Error('header checksum should be OK');
        if (!decoded.payloadChecksumOk) throw new Error('payload checksum should be OK');
        const expectedMajorOk = v.expectMajorVersionSupported ?? true;
        if (decoded.majorVersionSupported !== expectedMajorOk) {
          throw new Error(
            `majorVersionSupported: expected ${expectedMajorOk}, got ${decoded.majorVersionSupported}`
          );
        }
        if (v.record && !deepEqual(decoded.record, v.record)) {
          throw new Error(`decoded record mismatch for ${name}`);
        }
        if (v.expectFlags) {
          if (!deepEqual(decoded.header.flags, v.expectFlags)) {
            throw new Error(
              `flags mismatch for ${name}: ${JSON.stringify(decoded.header.flags)} != ${JSON.stringify(v.expectFlags)}`
            );
          }
        }
        console.log(`  PASS  ${name} (valid, decoded correctly)`);
        passed++;
      } else {
        try {
          await decodeBxpBinary(raw, { verify: true });
          console.log(`  FAIL  ${name}: expected BXPBinaryError, decode succeeded`);
          failed++;
        } catch (e) {
          if (e instanceof BXPBinaryError) {
            console.log(`  PASS  ${name} (correctly rejected: ${v.reason ?? ''})`);
            passed++;
          } else {
            throw e;
          }
        }
      }
    } catch (e) {
      console.log(`  FAIL  ${name}: ${e.message}`);
      failed++;
    }
  }

  console.log(`\n${passed} passed, ${failed} failed (TypeScript)`);
  process.exit(failed === 0 ? 0 : 1);
}

run();
