"""State persistence for idempotent scout runs.

Tracks processed repositories and run history to prevent duplicate
discovery work across scheduled runs.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


class ScoutState:
    """Persistent state manager with atomic writes and idempotency guards."""

    def __init__(self, state_path: str | Path | None = None) -> None:
        self.path = Path(state_path) if state_path else Path(".bxp/scout/state/state.json")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._data: dict[str, Any] = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {
                "version": "1.0.0",
                "created_at": time.time(),
                "last_run": None,
                "run_count": 0,
                "processed_repos": [],
                "searched_queries": [],
                "discoveries": [],
            }
        try:
            with self.path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            # Ensure required keys exist
            for key in ("processed_repos", "searched_queries", "discoveries", "run_count"):
                data.setdefault(key, [] if key != "run_count" else 0)
            return data
        except (json.JSONDecodeError, OSError):
            return {
                "version": "1.0.0",
                "created_at": time.time(),
                "last_run": None,
                "run_count": 0,
                "processed_repos": [],
                "searched_queries": [],
                "discoveries": [],
            }

    def save(self) -> None:
        """Atomically write state to disk."""
        tmp_path = self.path.with_suffix(".json.tmp")
        with tmp_path.open("w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2)
        tmp_path.replace(self.path)

    def is_processed(self, full_name: str) -> bool:
        return full_name in self._data.get("processed_repos", [])

    def mark_processed(self, full_name: str) -> None:
        repos = self._data.setdefault("processed_repos", [])
        if full_name not in repos:
            repos.append(full_name)

    def record_discovery(self, repo: dict[str, Any], score: float) -> None:
        discovery = {
            "full_name": repo["full_name"],
            "html_url": repo["html_url"],
            "score": score,
            "discovered_at": time.time(),
            "query": repo.get("query", ""),
        }
        self._data.setdefault("discoveries", []).append(discovery)

    def record_run(self, candidates_count: int) -> None:
        self._data["last_run"] = time.time()
        self._data["run_count"] = self._data.get("run_count", 0) + 1
        self._data.setdefault("run_history", []).append({
            "run_count": self._data["run_count"],
            "timestamp": time.time(),
            "candidates_found": candidates_count,
        })

    @property
    def run_count(self) -> int:
        return self._data.get("run_count", 0)

    @property
    def processed_count(self) -> int:
        return len(self._data.get("processed_repos", []))

    def to_dict(self) -> dict[str, Any]:
        return dict(self._data)
