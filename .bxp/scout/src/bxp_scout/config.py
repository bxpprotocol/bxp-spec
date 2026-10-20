"""Configuration loading and validation for BXP Integration Scout."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover - yaml optional at import, required at runtime
    yaml = None


class ScoutConfig:
    """Commercial-grade configuration manager with validation."""

    DEFAULTS = {
        "scout": {
            "name": "bxp-integration-scout",
            "version": "1.0.0",
            "mode": "read-only",
            "max_discoveries_per_run": 50,
            "max_candidates_per_report": 20,
            "min_score_threshold": 0.5,
        },
        "github": {
            "search_queries": [
                "air quality api",
                "air quality data",
                "atmospheric data",
                "pm25 sensor",
                "openaq",
                "airnow api",
                "environmental monitoring api",
                "weather air quality",
                "pollution data api",
                "aqicn",
            ],
            "sort": "updated",
            "order": "desc",
            "per_page": 10,
            "rate_limit_buffer": 10,
            "timeout_seconds": 30,
        },
        "scoring": {
            "weights": {
                "air_quality_keywords": 0.15,
                "api_data_keywords": 0.05,
                "stars": 0.10,
                "forks": 0.05,
                "open_license": 0.10,
                "recent_activity": 0.10,
            },
            "open_licenses": ["mit", "apache-2.0", "bsd-3-clause", "bsd-2-clause", "isc"],
            "recent_activity_days": 90,
        },
        "state": {
            "enabled": True,
            "path": ".bxp/scout/state/state.json",
            "prevent_duplicates": True,
        },
        "output": {
            "candidates_path": ".bxp/scout/state/candidates.json",
            "report_path": ".bxp/scout/reports/weekly-report.md",
            "adapters_path": ".bxp/scout/adapters",
            "log_path": ".bxp/scout/logs/scout.log",
        },
        "github_token_env": "GITHUB_TOKEN",
        "scheduling": {
            "cron": "0 2 * * *",
            "timezone": "UTC",
        },
        "adapters": {
            "enabled": True,
            "templates": ["openaq_to_bxp", "bxp_to_openaq", "generic_api_to_bxp"],
        },
        "human_review_required": True,
        "auto_pr_enabled": False,
    }

    def __init__(self, config_path: str | Path | None = None) -> None:
        self._config: dict[str, Any] = dict(self.DEFAULTS)
        self.config_path = Path(config_path) if config_path else None
        if config_path and Path(config_path).exists():
            self._load(config_path)

    def _load(self, config_path: str | Path) -> None:
        path = Path(config_path)
        if yaml is None:
            raise RuntimeError("PyYAML is required to load YAML configuration")
        with path.open("r", encoding="utf-8") as f:
            user_config = yaml.safe_load(f) or {}
        self._config = self._deep_merge(self.DEFAULTS, user_config)
        self._validate()

    @staticmethod
    def _deep_merge(base: dict, override: dict) -> dict:
        result = dict(base)
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = ScoutConfig._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    def _validate(self) -> None:
        required_sections = ["scout", "github", "scoring", "state", "output"]
        for section in required_sections:
            if section not in self._config:
                raise ValueError(f"Missing required config section: {section}")

        if self._config["scout"]["mode"] not in ("read-only", "assisted-pr"):
            raise ValueError("scout.mode must be 'read-only' or 'assisted-pr'")

        if self._config.get("auto_pr_enabled", False):
            raise ValueError("auto_pr_enabled must be false — human review required for PRs")

    def get(self, key: str, default: Any = None) -> Any:
        """Get config value using dot notation (e.g. 'github.timeout_seconds')."""
        parts = key.split(".")
        current: Any = self._config
        for part in parts:
            if not isinstance(current, dict) or part not in current:
                return default
            current = current[part]
        return current

    def as_dict(self) -> dict[str, Any]:
        return dict(self._config)

    @property
    def github_token(self) -> str | None:
        env_var = self.get("github_token_env", "GITHUB_TOKEN")
        return os.environ.get(env_var)

    @property
    def repo_root(self) -> Path:
        return Path(__file__).resolve().parent.parent.parent.parent
