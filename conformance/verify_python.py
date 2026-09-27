#!/usr/bin/env python3
"""
Verifies sdk/python/bxp_binary.py against conformance/manifest.json.

For every "expectValid": true vector, decoding must succeed, checksums
must be OK, majorVersionSupported must match, and (for the ones that
carry a "record") the decoded record must equal the expected record
exactly.

For every "expectValid": false vector, decode_bxp_binary(raw, verify=True)
must raise BXPBinaryError -- never crash with something else, never
silently succeed.

Run with: python3 conformance/verify_python.py
Exit code is 0 iff every vector matches expectations.
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
sys.path.insert(0, str(REPO_ROOT / "sdk" / "python"))

from bxp_binary import decode_bxp_binary, BXPBinaryError  # noqa: E402

MANIFEST = json.loads((HERE / "manifest.json").read_text())


def run() -> int:
    passed = failed = 0
    for v in MANIFEST["vectors"]:
        path = HERE / "vectors" / v["file"]
        raw = path.read_bytes()
        name = v["file"]
        try:
            if v["expectValid"]:
                decoded = decode_bxp_binary(raw, verify=True)
                assert decoded["headerChecksumOk"], "header checksum should be OK"
                assert decoded["payloadChecksumOk"], "payload checksum should be OK"
                expected_major_ok = v.get("expectMajorVersionSupported", True)
                assert decoded["majorVersionSupported"] == expected_major_ok, (
                    f"majorVersionSupported: expected {expected_major_ok}, "
                    f"got {decoded['majorVersionSupported']}"
                )
                if "record" in v:
                    assert decoded["record"] == v["record"], (
                        f"decoded record mismatch for {name}"
                    )
                if "expectFlags" in v:
                    assert decoded["header"]["flags"] == v["expectFlags"], (
                        f"flags mismatch for {name}: "
                        f"{decoded['header']['flags']} != {v['expectFlags']}"
                    )
                print(f"  PASS  {name} (valid, decoded correctly)")
                passed += 1
            else:
                try:
                    decode_bxp_binary(raw, verify=True)
                except BXPBinaryError:
                    print(f"  PASS  {name} (correctly rejected: {v.get('reason', '')})")
                    passed += 1
                else:
                    print(f"  FAIL  {name}: expected BXPBinaryError, decode succeeded")
                    failed += 1
        except AssertionError as e:
            print(f"  FAIL  {name}: {e}")
            failed += 1
        except Exception as e:
            print(f"  FAIL  {name}: unexpected {type(e).__name__}: {e}")
            failed += 1

    print(f"\n{passed} passed, {failed} failed (Python)")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(run())
