"""CLI entry point for BXP Integration Scout.

Usage:
    python -m bxp_scout discover
    python -m bxp_scout report
    python -m bxp_scout run        # Full pipeline: discover + score + report
    python -m bxp_scout adapters   # Generate adapter drafts
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from .adapter import AdapterGenerator
from .config import ScoutConfig
from .discovery import GitHubDiscovery
from .report import ReportGenerator
from .scoring import RepoScorer
from .scout_logging import ScoutLogger
from .state import ScoutState


def run_discovery(config: ScoutConfig, logger: ScoutLogger, state: ScoutState) -> list[dict]:
    """Run discovery and scoring pipeline."""
    queries = config.get("github.search_queries", [])
    max_results = config.get("scout.max_discoveries_per_run", 50)

    discovery = GitHubDiscovery(config, logger)
    repos = discovery.discover(queries=queries, max_results=max_results)

    # Filter already-processed repos
    new_repos = [r for r in repos if not state.is_processed(r.get("full_name", ""))]
    logger.info(f"{len(new_repos)} new repositories after dedup (of {len(repos)} total)")

    # Score
    scorer = RepoScorer(config, logger)
    candidates = scorer.assess(new_repos)

    # Record discoveries and mark processed
    for repo in new_repos:
        state.mark_processed(repo.get("full_name", ""))
    for candidate in candidates:
        state.record_discovery(candidate, candidate.get("score", 0))

    state.record_run(len(candidates))
    state.save()

    return candidates


def run_report(config: ScoutConfig, logger: ScoutLogger, candidates: list[dict], state: ScoutState) -> None:
    """Generate the weekly report."""
    generator = ReportGenerator(config, logger)
    generator.generate(
        candidates=candidates,
        state=state,
        run_count=state.run_count,
        generated_at=time.time(),
    )


def run_adapters(config: ScoutConfig, logger: ScoutLogger, candidates: list[dict]) -> None:
    """Generate adapter drafts for top candidates."""
    if not config.get("adapters.enabled", True):
        return
    generator = AdapterGenerator(config, logger)
    top_n = min(5, len(candidates))
    for candidate in candidates[:top_n]:
        generator.generate_for_candidate(candidate)


def main() -> int:
    parser = argparse.ArgumentParser(description="BXP Integration Scout")
    parser.add_argument("command", choices=["discover", "report", "run", "adapters"], help="Command to run")
    parser.add_argument("--config", default=".bxp/scout/config.yaml", help="Path to config.yaml")
    args = parser.parse_args()

    config = ScoutConfig(args.config)
    logger = ScoutLogger(log_path=config.get("output.log_path"))
    state = ScoutState(config.get("state.path"))

    logger.info(f"BXP Integration Scout v{config.get('scout.version', '1.0.0')} starting")

    candidates: list[dict] = []

    if args.command in ("discover", "run"):
        candidates = run_discovery(config, logger, state)
        logger.info(f"Discovery complete: {len(candidates)} candidates")

    if args.command in ("report", "run"):
        if not candidates:
            # Load previous candidates if report-only
            candidates_path = Path(config.get("output.candidates_path", ".bxp/scout/state/candidates.json"))
            if candidates_path.exists():
                candidates = json.loads(candidates_path.read_text(encoding="utf-8"))
        run_report(config, logger, candidates, state)

    if args.command in ("adapters", "run"):
        if not candidates:
            candidates_path = Path(config.get("output.candidates_path", ".bxp/scout/state/candidates.json"))
            if candidates_path.exists():
                candidates = json.loads(candidates_path.read_text(encoding="utf-8"))
        run_adapters(config, logger, candidates)

    logger.info("BXP Integration Scout finished")
    return 0


if __name__ == "__main__":
    sys.exit(main())
