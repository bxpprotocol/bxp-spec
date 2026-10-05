#!/usr/bin/env python3
"""Validate pyproject.toml with a strict TOML parser.

Python 3.10 ships no `tomllib`, so an invalid pyproject.toml went unnoticed for
the life of the project: setuptools fell back to a lenient parser and pytest,
which reads this file as its configuration, tolerated it. Python 3.11 added
`tomllib`, which is strict, and from that version the file failed to parse
outright. The server tests passed on 3.10 and failed on every CI run on 3.11+,
with the real cause invisible from the test output.

The offending constructs were a multi-line inline table and a trailing comma,
both forbidden by TOML 1.0.

This check uses `tomllib` where available and falls back to `tomli`, so it runs
on any interpreter the project supports. It additionally asserts the packaging
declarations that the published distribution depends on, because those were
wrong at the same time: `packages.find` finds nothing when the SDK is plain
modules, which is how the wheel shipped with no code in it.

    python scripts/check_pyproject.py
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:
    try:
        import tomli as tomllib  # type: ignore
    except ModuleNotFoundError:
        tomllib = None  # type: ignore

failures: list[str] = []


def fail(msg: str) -> None:
    failures.append(msg)


def main() -> int:
    path = REPO / "pyproject.toml"
    raw = path.read_bytes()

    if tomllib is None:
        print("WARN  no tomllib or tomli available; cannot validate strictly")
        print("WARN  install with: pip install tomli")
        return 0

    try:
        doc = tomllib.loads(raw.decode("utf-8"))
    except Exception as e:  # noqa: BLE001 - surface whatever the parser says
        print(f"FAIL  pyproject.toml is not valid TOML: {e}")
        print()
        print("  Python 3.10 and earlier tolerate malformed TOML. 3.11+ do not,")
        print("  and pytest reads this file as its configuration, so a parse")
        print("  failure presents as every test erroring before collection.")
        return 1

    print("OK    pyproject.toml parses under a strict TOML parser")

    project = doc.get("project") or {}
    tool = doc.get("tool", {}).get("setuptools", {})

    # The distribution must declare flat modules, not packages. The SDK is
    # single-file modules, so packages.find locates nothing and the wheel ships
    # metadata only.
    modules = tool.get("py-modules")
    packages = doc.get("tool", {}).get("setuptools", {}).get("packages")
    if not modules and not packages:
        fail(
            "[tool.setuptools] declares neither py-modules nor packages. The "
            "SDK is single-file modules; without py-modules the wheel contains "
            "no code."
        )
    if modules:
        expected = {"bxp_sdk", "bxp_binary", "bxp_cli"}
        missing = expected - set(modules)
        if missing:
            fail(f"py-modules is missing {sorted(missing)}")
        else:
            print(f"OK    py-modules declares {', '.join(sorted(modules))}")

    # Every console script must resolve to a declared module.
    for name, target in (project.get("scripts") or {}).items():
        mod = target.split(":")[0]
        if modules and mod not in modules and mod not in (packages or []):
            fail(
                f"console script {name!r} targets {mod!r}, which is not "
                f"declared in py-modules or packages. It would install and "
                f"then fail on invocation."
            )

    # Licence must be a PEP 639 SPDX expression. The deprecated trove classifier
    # alongside {text=...} is rejected by current setuptools.
    lic = project.get("license")
    if isinstance(lic, dict):
        fail(
            'license = {text = "..."} is the deprecated form. Use the SPDX '
            'string form: license = "Apache-2.0"'
        )
    elif not isinstance(lic, str):
        fail("no license declared")
    else:
        print(f"OK    license is the SPDX string {lic!r}")

    for c in project.get("classifiers", []):
        if str(c).startswith("License ::"):
            fail(
                f"deprecated licence classifier {c!r} remains. PEP 639 "
                f"replaces it with the license field."
            )

    # Python floor must agree with the classifiers.
    floor = str(project.get("requires-python", ""))
    if floor.startswith(">=3."):
        minor = int(floor[4:].split(".")[0])
        for c in project.get("classifiers", []):
            if str(c).startswith("Programming Language :: Python :: 3."):
                cminor = int(str(c).rsplit(".", 1)[1])
                if cminor < minor:
                    fail(
                        f"classifier claims Python 3.{cminor} but "
                        f"requires-python is {floor}"
                    )
        print(f"OK    requires-python {floor} agrees with the classifiers")

    print()
    if failures:
        print(f"FAIL  {len(failures)} problem(s):")
        for f in failures:
            print("  -", f)
        return 1

    print("OK    packaging declarations are consistent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())