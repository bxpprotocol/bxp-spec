#!/usr/bin/env python3
"""Pre-flight verification for publishing BXP to package registries.

Publishing a package that cannot be imported is worse than not publishing it:
`pip install bxp-sdk` would succeed, `import bxp_sdk` would fail, and the
project's first impression in the Python ecosystem would be a broken
distribution. That is not hypothetical here. The wheel built from this
repository used to contain metadata only, and the npm tarball shipped only
package.json, because `packages.find` finds no directories when the SDK is
plain modules and `files: ["dist"]` ships nothing when `tsc` has not run.

So this checks the artefacts the way a consumer would experience them: build,
install into a clean virtual environment, import, and exercise the API.

    python scripts/verify_packages.py

Requires network access for the venv installs. Exit code is non-zero on any
failure. Run this before every publish, and in CI.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DIST = REPO / "dist"
failures: list[str] = []


def run(cmd: list[str], cwd: Path | None = None, timeout: int = 600) -> subprocess.CompletedProcess:
    # On Windows the npm entry point is npm.cmd, which subprocess will not
    # resolve through PATH without the extension.
    if cmd and cmd[0] in ("npm", "npx"):
        exe = shutil.which(cmd[0]) or shutil.which(f"{cmd[0]}.cmd")
        if exe is None:
            return subprocess.CompletedProcess(cmd, 127, "", "npm not found on PATH")
        cmd = [exe, *cmd[1:]]
    return subprocess.run(
        cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, shell=False
    )


def fail(msg: str) -> None:
    failures.append(msg)
    print(f"FAIL  {msg}")


def ok(msg: str) -> None:
    print(f"OK    {msg}")


# ── Python ────────────────────────────────────────────────────────────────

def check_python() -> None:
    print("\nPython distribution")
    for stale in ("dist", "build"):
        shutil.rmtree(REPO / stale, ignore_errors=True)

    r = run([sys.executable, "-m", "build"])
    if r.returncode != 0:
        fail(f"`python -m build` failed:\n{r.stdout[-800:]}{r.stderr[-800:]}")
        return

    wheels = sorted(DIST.glob("*.whl"))
    if not wheels:
        fail("no wheel produced")
        return
    wheel = wheels[-1]

    names = zipfile.ZipFile(wheel).namelist()
    modules = [n for n in names if n.endswith(".py")]
    if not modules:
        fail(
            f"{wheel.name} contains no Python modules — only "
            f"{[n for n in names if not n.startswith(REPO.name)]}. "
            f"This is the empty-wheel bug: check [tool.setuptools] py-modules."
        )
        return
    ok(f"{wheel.name} ships {len(modules)} module(s): {', '.join(modules)}")

    expected = {"bxp_sdk.py", "bxp_binary.py", "bxp_cli.py"}
    missing = expected - set(modules)
    if missing:
        fail(f"{wheel.name} is missing expected modules: {sorted(missing)}")

    # Install into a clean environment and use it as a consumer would.
    with tempfile.TemporaryDirectory() as td:
        venv = Path(td) / "venv"
        r = run([sys.executable, "-m", "venv", str(venv)], timeout=300)
        if r.returncode != 0:
            fail(f"could not create venv: {r.stderr[-400:]}")
            return
        py = venv / ("Scripts" if sys.platform == "win32" else "bin") / "python"

        r = run([str(py), "-m", "pip", "install", "--quiet", "--no-input", str(wheel)], timeout=600)
        if r.returncode != 0:
            fail(f"wheel would not install:\n{r.stdout[-600:]}{r.stderr[-600:]}")
            return
        ok("wheel installs into a clean venv")

        probe = (
            "import bxp_sdk, bxp_binary, bxp_cli;"
            "assert hasattr(bxp_sdk,'write_bxp');"
            "assert hasattr(bxp_sdk,'calculate_risk');"
            "assert hasattr(bxp_binary,'encode_bxp_binary');"
            "print('api ok')"
        )
        r = run([str(py), "-c", probe], timeout=180)
        if r.returncode != 0:
            fail(f"installed package is not importable/usable:\n{r.stderr[-800:]}")
            return
        ok("installed package imports and exposes the documented API")

        # The console script must exist and run, not merely be declared.
        script_dir = venv / ("Scripts" if sys.platform == "win32" else "bin")
        exe = script_dir / ("bxp.exe" if sys.platform == "win32" else "bxp")
        if not exe.exists():
            fail("console script 'bxp' was not installed")
            return
        r = run([str(exe), "--help"], timeout=180)
        if r.returncode != 0:
            fail(f"console script 'bxp --help' failed:\n{r.stderr[-400:]}")
            return
        ok("console script 'bxp' runs")

    # Metadata that registries and downstream tooling read.
    meta = zipfile.ZipFile(wheel).read(
        next(n for n in names if n.endswith("METADATA"))
    ).decode()
    for field, needle in [
        ("license", "License-Expression: Apache-2.0"),
        ("summary", "Summary:"),
        ("author", "Author-email:"),
        ("project urls", "Project-URL:"),
        ("python requirement", "Requires-Python:"),
    ]:
        if needle not in meta:
            fail(f"wheel METADATA missing {field} (expected {needle!r})")
    ok("wheel METADATA carries licence, summary, author, urls, python requirement")


# ── TypeScript ────────────────────────────────────────────────────────────

def check_typescript() -> None:
    print("\nTypeScript distribution")
    ts = REPO / "sdk" / "typescript"
    if not (ts / "package.json").exists():
        fail("sdk/typescript/package.json missing")
        return

    r = run(["npm", "install", "--no-audit", "--no-fund"], cwd=ts, timeout=900)
    if r.returncode != 0:
        fail(f"npm install failed:\n{r.stderr[-600:]}")
        return

    r = run(["npm", "run", "build"], cwd=ts, timeout=600)
    if r.returncode != 0:
        fail(f"npm run build failed — 'files: [\"dist\"]' would ship nothing:\n{r.stderr[-600:]}")
        return

    dist = ts / "dist"
    built = sorted(p.name for p in dist.glob("*.js")) if dist.exists() else []
    if not built:
        fail("dist/ contains no JavaScript after a successful build")
        return
    if not list(dist.glob("*.d.ts")):
        fail("dist/ contains no type declarations; package.json advertises 'types'")
    ok(f"dist/ contains {', '.join(built)}")

    r = run(["npm", "pack", "--dry-run", "--json"], cwd=ts, timeout=600)
    if r.returncode != 0:
        fail(f"npm pack --dry-run failed:\n{r.stderr[-400:]}")
        return
    try:
        meta = json.loads(r.stdout)
        files = [f["path"] for f in meta[0]["files"]]
    except (json.JSONDecodeError, IndexError, KeyError):
        fail("could not parse npm pack --dry-run --json output")
        return

    code = [f for f in files if f.endswith((".js", ".d.ts"))]
    if not code:
        fail(f"tarball contains no built code, only: {files}")
        return
    ok(f"tarball ships {len(code)} built file(s)")

    pkg = json.loads((ts / "package.json").read_text(encoding="utf-8"))
    missing = pkg.get("dependencies", {})
    for dep in missing:
        if dep not in code and "node_modules" in dep:
            continue

    # Install the tarball into a scratch project and import it.
    r = run(["npm", "pack"], cwd=ts, timeout=600)
    if r.returncode != 0:
        fail("npm pack failed")
        return
    tarballs = sorted(ts.glob("*.tgz"))
    if not tarballs:
        fail("npm pack produced no tarball")
        return
    tarball = tarballs[-1]

    with tempfile.TemporaryDirectory() as td:
        scratch = Path(td)
        run(["npm", "init", "-y"], cwd=scratch, timeout=300)
        r = run(["npm", "install", str(tarball)], cwd=scratch, timeout=600)
        if r.returncode != 0:
            fail(f"tarball would not install:\n{r.stderr[-600:]}")
            tarball.unlink(missing_ok=True)
            return
        ok("tarball installs into a clean project")

        probe = (
            "import('@bxp/sdk').then(m=>{"
            "if(typeof m.writeBxp!=='function'&&typeof m.write_bxp!=='function')"
            "{console.error('no write function exported');process.exit(1)}"
            "console.log('exports:'+Object.keys(m).length)}).catch(e=>"
            "{console.error(e.message);process.exit(1)})"
        )
        r = run(["node", "-e", probe], cwd=scratch, timeout=300)
        if r.returncode != 0:
            fail(f"installed tarball is not importable:\n{r.stdout[-400:]}{r.stderr[-400:]}")
        else:
            ok(f"installed tarball imports: {r.stdout.strip()}")

    tarball.unlink(missing_ok=True)


def main() -> int:
    print("Verifying publishable artefacts the way a consumer experiences them.\n")
    check_python()
    check_typescript()

    print()
    if failures:
        print(f"{len(failures)} check(s) failed. Do not publish.")
        return 1
    print("All packaging checks passed. Artefacts are safe to publish.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())