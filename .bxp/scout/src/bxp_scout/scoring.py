"""Scoring and assessment of discovered repositories.

Scores repositories 0-1 based on BXP integration fit using configurable
weights. Never fabricates metrics — only uses observable GitHub data.
"""

from __future__ import annotations

import time
from typing import Any

from .config import ScoutConfig
from .scout_logging import ScoutLogger


class RepoScorer:
    """Scores repositories for BXP integration potential."""

    def __init__(self, config: ScoutConfig, logger: ScoutLogger) -> None:
        self.config = config
        self.logger = logger
        self.weights = config.get("scoring.weights", {})
        self.open_licenses = set(config.get("scoring.open_licenses", []))
        self.recent_days = config.get("scoring.recent_activity_days", 90)

    def score(self, repo: dict[str, Any]) -> float:
        """Score a repository 0-1 for BXP integration fit."""
        score = 0.0
        text = f"{repo.get('description', '')} {' '.join(repo.get('topics', []))}".lower()

        # Air quality / atmospheric keywords
        aq_keywords = ("air quality", "pm2", "pollution", "atmospheric", "aqi", "openaq", "airnow", "environmental")
        aq_matches = sum(1 for kw in aq_keywords if kw in text)
        score += min(aq_matches * self.weights.get("air_quality_keywords", 0.15), 0.45)

        # API / data focus (concrete integration surface)
        api_keywords = ("api", "data", "sensor", "monitoring", "feed", "export", "format", "sdk", "library")
        api_matches = sum(1 for kw in api_keywords if kw in text)
        score += min(api_matches * self.weights.get("api_data_keywords", 0.05), 0.25)

        # Stars signal community interest
        stars = repo.get("stars", 0)
        if stars > 1000:
            score += self.weights.get("stars", 0.10)
        elif stars > 100:
            score += self.weights.get("stars", 0.10) * 0.5
        elif stars > 10:
            score += self.weights.get("stars", 0.10) * 0.25

        # Forks signal reuse
        forks = repo.get("forks", 0)
        if forks > 50:
            score += self.weights.get("forks", 0.05)
        elif forks > 10:
            score += self.weights.get("forks", 0.05) * 0.5

        # Open license enables reuse
        license_id = (repo.get("license") or "").lower()
        if license_id in self.open_licenses:
            score += self.weights.get("open_license", 0.10)

        # Recently updated (active maintenance)
        updated_at = repo.get("updated_at", "")
        if updated_at:
            try:
                t = time.strptime(updated_at, "%Y-%m-%dT%H:%M:%SZ")
                days = (time.time() - time.mktime(t)) / 86400
                if days < 30:
                    score += self.weights.get("recent_activity", 0.10)
                elif days < self.recent_days:
                    score += self.weights.get("recent_activity", 0.10) * 0.5
            except (ValueError, OSError):
                pass

        return min(score, 1.0)

    def assess(self, repos: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Score and sort repositories. Returns top candidates."""
        for repo in repos:
            repo["score"] = self.score(repo)
            repo["score_breakdown"] = self._breakdown(repo)

        repos.sort(key=lambda r: r.get("score", 0), reverse=True)
        threshold = self.config.get("scout.min_score_threshold", 0.5)
        qualified = [r for r in repos if r.get("score", 0) >= threshold]
        max_candidates = self.config.get("scout.max_candidates_per_report", 20)
        return qualified[:max_candidates]

    def _breakdown(self, repo: dict[str, Any]) -> dict[str, float]:
        """Return per-component score breakdown for transparency."""
        text = f"{repo.get('description', '')} {' '.join(repo.get('topics', []))}".lower()
        aq_keywords = ("air quality", "pm2", "pollution", "atmospheric", "aqi", "openaq", "airnow", "environmental")
        api_keywords = ("api", "data", "sensor", "monitoring", "feed", "export", "format", "sdk", "library")

        return {
            "air_quality_relevance": min(
                sum(1 for kw in aq_keywords if kw in text) * self.weights.get("air_quality_keywords", 0.15), 0.45
            ),
            "api_data_surface": min(
                sum(1 for kw in api_keywords if kw in text) * self.weights.get("api_data_keywords", 0.05), 0.25
            ),
            "community_stars": self._stars_component(repo.get("stars", 0)),
            "forks_reuse": self._forks_component(repo.get("forks", 0)),
            "open_license": self.weights.get("open_license", 0.10)
            if (repo.get("license") or "").lower() in self.open_licenses
            else 0.0,
            "recent_activity": self._activity_component(repo.get("updated_at", "")),
        }

    @staticmethod
    def _stars_component(stars: int) -> float:
        if stars > 1000:
            return 0.10
        if stars > 100:
            return 0.05
        if stars > 10:
            return 0.025
        return 0.0

    @staticmethod
    def _forks_component(forks: int) -> float:
        if forks > 50:
            return 0.05
        if forks > 10:
            return 0.025
        return 0.0

    @staticmethod
    def _activity_component(updated_at: str) -> float:
        if not updated_at:
            return 0.0
        try:
            import time as _time
            t = _time.strptime(updated_at, "%Y-%m-%dT%H:%M:%SZ")
            days = (_time.time() - _time.mktime(t)) / 86400
            if days < 30:
                return 0.10
            if days < 90:
                return 0.05
        except (ValueError, OSError):
            pass
        return 0.0
