# BXP Integration Scout

Commercial-grade, read-only discovery agent for identifying BXP integration
opportunities in existing atmospheric-data projects.

## Purpose

The BXP Integration Scout discovers open-source projects working with
atmospheric or air-quality data, scores them for BXP integration fit, and
generates adapter drafts — all without modifying external repositories.

**Core principle:** Make BXP useful inside existing projects. Do not merely
advertise BXP or generate activity in its own repositories. Human review is
required before any PR is opened to an external repo.

## Architecture

```
.bxp/scout/
├── config.yaml              # Configuration (commercial-grade)
├── requirements.txt         # Python dependencies
├── src/
│   ├── __init__.py          # Package metadata
│   ├── __main__.py          # `python -m bxp_scout` entry point
│   ├── cli.py               # CLI commands: discover, report, run, adapters
│   ├── config.py            # Configuration loading + validation
│   ├── state.py             # Persistent state (idempotency, dedup)
│   ├── discovery.py         # Read-only GitHub repository search
│   ├── scoring.py           # 0-1 BXP fit scoring
│   ├── adapter.py           # Adapter/integration template generator
│   ├── report.py            # Weekly markdown report
│   └── logging.py           # Structured logging
├── adapters/                # Generated adapter drafts (human review)
├── state/                   # Persistent state (dedup, run history)
├── reports/                 # Weekly reports
└── logs/                    # Log files
```

## Commands

```bash
# Full pipeline: discover → score → report → adapters
python -m bxp_scout run

# Discovery only
python -m bxp_scout discover

# Report only (uses last cached candidates)
python -m bxp_scout report

# Adapter drafts only
python -m bxp_scout adapters
```

## Configuration

Edit `.bxp/scout/config.yaml` to adjust:
- GitHub search queries
- Scoring weights
- Rate limits and timeouts
- Output paths
- Scheduling cron

## Key Safeguards

| Safeguard | Implementation |
|-----------|---------------|
| Read-only mode | Scout only reads GitHub API; never writes to external repos |
| No auto-PR | `auto_pr_enabled: false` — human must open PRs manually |
| Idempotency | State file tracks processed repos to prevent duplicates |
| Rate limiting | 1-second delay between queries; respects GitHub API limits |
| Human review | Every adapter draft marked `human_review_required: true` |
| No fabricated metrics | Scores use only observable GitHub data |

## Workflow

1. Scout runs on schedule (weekly) or manually
2. Discovers up to 50 repositories across 10 search queries
3. Scores each 0-1 for BXP integration fit
4. Generates adapter drafts for top 5 candidates
5. Writes weekly report to `.bxp/scout/reports/weekly-report.md`
6. Human reviews report, selects candidates, opens PRs manually

## Success Metric

Independently maintained integrations and actual external usage — not
stars, commits, or pull-request volume.

## License

Apache 2.0 — part of the BXP Protocol.
