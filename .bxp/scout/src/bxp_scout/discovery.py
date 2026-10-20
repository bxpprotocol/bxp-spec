"""Read-only GitHub repository discovery for atmospheric-data projects.

Uses the GitHub Search API to find relevant repositories. Never modifies
external repositories. Respects rate limits and uses optional authentication.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .config import ScoutConfig
from .scout_logging import ScoutLogger


class GitHubDiscovery:
    """Read-only discovery of atmospheric-data repositories on GitHub."""

    def __init__(self, config: ScoutConfig, logger: ScoutLogger) -> None:
        self.config = config
        self.logger = logger
        self.token = config.github_token
        self.timeout = config.get("github.timeout_seconds", 30)
        self.per_page = config.get("github.per_page", 10)
        self.rate_limit_buffer = config.get("github.rate_limit_buffer", 10)

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "bxp-integration-scout/1.0.0",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _get(self, url: str) -> dict[str, Any] | None:
        """Perform a GET request with error handling and rate-limit awareness."""
        req = urllib.request.Request(url, headers=self._headers())
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 403:
                self.logger.warning("GitHub API rate limit hit (403). Consider setting GITHUB_TOKEN.")
            elif exc.code == 401:
                self.logger.warning("GitHub API authentication failed (401). Check GITHUB_TOKEN.")
            else:
                self.logger.error(f"GitHub API error {exc.code} for {url}")
            return None
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
            self.logger.error(f"Request failed for {url}: {exc}")
            return None

    def search_repositories(self, query: str, page: int = 1) -> list[dict[str, Any]]:
        """Search GitHub for repositories matching a query. Read-only."""
        encoded_query = urllib.parse.quote(query)
        url = (
            f"https://api.github.com/search/repositories"
            f"?q={encoded_query}"
            f"&sort={self.config.get('github.sort', 'updated')}"
            f"&order={self.config.get('github.order', 'desc')}"
            f"&per_page={self.per_page}"
            f"&page={page}"
        )
        self.logger.info(f"Searching GitHub: {query} (page {page})")
        data = self._get(url)
        if data is None:
            return []
        items = data.get("items", [])
        results = []
        for item in items:
            results.append({
                "full_name": item.get("full_name", ""),
                "html_url": item.get("html_url", ""),
                "description": item.get("description") or "",
                "language": item.get("language"),
                "stars": item.get("stargazers_count", 0),
                "forks": item.get("forks_count", 0),
                "updated_at": item.get("updated_at", ""),
                "topics": item.get("topics", []),
                "license": (item.get("license") or {}).get("spdx_id") if item.get("license") else None,
                "query": query,
            })
        return results

    def discover(self, queries: list[str] | None = None, max_results: int = 50) -> list[dict[str, Any]]:
        """Run discovery across all configured queries. Deduplicates results."""
        queries = queries or self.config.get("github.search_queries", [])
        seen: set[str] = set()
        results: list[dict[str, Any]] = []

        for query in queries:
            if len(results) >= max_results:
                break
            page_results = self.search_repositories(query)
            for repo in page_results:
                if len(results) >= max_results:
                    break
                full_name = repo.get("full_name", "")
                if full_name and full_name not in seen:
                    seen.add(full_name)
                    results.append(repo)
            # Be respectful of rate limits between queries
            time.sleep(1)

        self.logger.info(f"Discovery complete: {len(results)} unique repositories found")
        return results
