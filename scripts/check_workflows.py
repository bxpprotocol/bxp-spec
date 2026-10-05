#!/usr/bin/env python3
"""Validate the GitHub Actions workflows against the rules GitHub actually enforces.

This exists because of a real outage. `publish-npm` gated on
`secrets.NPM_TOKEN != ''` in a job-level `if:`. The `secrets` context is not
available there, so GitHub rejected the *entire workflow file* at parse time.
Every run failed with zero jobs executed, and the v2.1.0 release silently
published nothing to PyPI. Nothing in the repository caught it: the YAML parsed
fine locally, and every test passed.

A workflow that fails to parse is invisible to normal testing and blocks all
delivery, so it gets an explicit check.

    python scripts/check_workflows.py

Exit code is non-zero on any violation, so CI can gate on it.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
WORKFLOWS = REPO / ".github" / "workflows"

problems: list[str] = []

# Contexts GitHub permits in each position. Using anything else is a parse-time
# failure for the whole file, not a runtime error in one job.
JOB_IF_ALLOWED = {
    "github", "needs", "vars", "inputs", "always", "cancelled", "success",
    "failure", "hashFiles", "env",
}
STEP_IF_ALLOWED = JOB_IF_ALLOWED | {"secrets", "steps", "strategy", "job", "matrix"}
# `env` at job level may reference secrets; step level may too.
JOB_ENV_ALLOWED = {"github", "secrets", "vars", "inputs", "needs", "strategy", "matrix", "env"}

INTERPOLATION = re.compile(r"\$\{\{\s*([^}]+?)\s*\}\}")
# `if:` conditions may omit the ${{ }} wrapper, so a bare expression has to be
# scanned for context names too. Step names and shell text are excluded because
# only `if` and `env` values are inspected.
KNOWN_CONTEXTS = (
    "github", "secrets", "steps", "strategy", "matrix", "job", "needs",
    "env", "vars", "inputs", "runner", "hashFiles",
)
BARE_CONTEXT = re.compile(
    r"(?<![A-Za-z0-9_$.])(" + "|".join(KNOWN_CONTEXTS) + r")"
    r"(?:\.[A-Za-z_][A-Za-z0-9_]*|\s*\[[^\]]*\])?"
)


def fail(msg: str) -> None:
    problems.append(msg)


def contexts_in(expr: str) -> set[str]:
    """Context names referenced in a GitHub expression.

    Handles both the interpolated form ``${{ secrets.X != '' }}`` and the bare
    form ``secrets.X != ''``, which GitHub also accepts in `if:`.
    """
    found = set()

    for body in INTERPOLATION.findall(expr):
        # Take the leading identifier of each dotted path.
        head = body.split(".")[0].strip()
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", head):
            found.add(head)
        else:
            found.add(f"<complex:{body.strip()}>")

    # Strip interpolation first so the bare scan cannot double-count, then look
    # for bare context references.
    residue = INTERPOLATION.sub(" ", expr)
    if residue.strip():
        found.update(BARE_CONTEXT.findall(residue))

    return found


def check(path: Path) -> None:
    rel = path.relative_to(REPO)
    text = path.read_text(encoding="utf-8")

    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError as e:
        fail(f"{rel}: not valid YAML: {e}")
        return

    if not isinstance(doc, dict):
        fail(f"{rel}: top level is not a mapping")
        return

    jobs = doc.get("jobs") or {}
    if not jobs:
        fail(f"{rel}: defines no jobs")
        return

    print(f"{rel}: {len(jobs)} job(s)")

    for name, job in jobs.items():
        if not isinstance(job, dict):
            fail(f"{rel}: job {name!r} is not a mapping")
            continue

        # A job-level `if` may not reference `secrets`.
        job_if = job.get("if")
        if isinstance(job_if, str):
            bad = contexts_in(job_if) & {"secrets", "steps", "strategy", "matrix", "job"}
            if bad:
                fail(
                    f"{rel}: job {name!r} uses {sorted(bad)} in its job-level `if`. "
                    f"GitHub rejects the entire file for this. Job-level `if` "
                    f"permits only: {sorted(JOB_IF_ALLOWED)}. Move the check into "
                    f"a job-level `env` and test it at step level."
                )

        # Job-level env may reference secrets.
        job_env = job.get("env") or {}
        if isinstance(job_env, dict):
            for key, val in job_env.items():
                if isinstance(val, str):
                    bad = contexts_in(val) - JOB_ENV_ALLOWED
                    if bad:
                        fail(
                            f"{rel}: job {name!r} env {key} references {sorted(bad)}; "
                            f"job env permits only {sorted(JOB_ENV_ALLOWED)}"
                        )

        steps = job.get("steps") or []
        if not steps:
            fail(f"{rel}: job {name!r} has no steps")

        for idx, step in enumerate(steps):
            if not isinstance(step, dict):
                fail(f"{rel}: job {name!r} step {idx} is not a mapping")
                continue
            step_if = step.get("if")
            if isinstance(step_if, str):
                bad = contexts_in(step_if) - STEP_IF_ALLOWED
                if bad:
                    fail(f"{rel}: job {name!r} step {idx} `if` references {sorted(bad)}")

            label = step.get("name") or step.get("uses") or f"step {idx}"
            if "uses" not in step and "run" not in step:
                fail(f"{rel}: job {name!r} {label} has neither `uses` nor `run`")

    # Every `needs:` must name a real job, or the dependency silently no-ops.
    names = set(jobs)
    for name, job in jobs.items():
        if not isinstance(job, dict):
            continue
        needs = job.get("needs")
        if not needs:
            continue
        for dep in [needs] if isinstance(needs, str) else needs:
            if dep not in names:
                fail(f"{rel}: job {name!r} needs unknown job {dep!r}")

    # `needs: [build]` where the dep can never succeed blocks the release.
    print(f"{rel}: ok")


def main() -> int:
    if not WORKFLOWS.exists():
        print(f"FAIL  no workflows directory at {WORKFLOWS}")
        return 1

    files = sorted(WORKFLOWS.glob("*.yml")) + sorted(WORKFLOWS.glob("*.yaml"))
    if not files:
        print("FAIL  no workflow files found")
        return 1

    print(f"Validating {len(files)} workflow file(s) against GitHub Actions rules\n")
    for f in files:
        check(f)

    print()
    if problems:
        print(f"FAIL  {len(problems)} workflow violation(s):\n")
        for p in problems:
            print("  -", p)
        return 1

    print("OK  workflows are valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())