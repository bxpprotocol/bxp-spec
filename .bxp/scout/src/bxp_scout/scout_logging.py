"""Structured logging for BXP Integration Scout."""

from __future__ import annotations

import logging
import sys
from pathlib import Path


class ScoutLogger:
    """Wrapper around Python logging with structured output."""

    def __init__(self, name: str = "bxp-scout", log_path: str | Path | None = None) -> None:
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False

        # Clear existing handlers to avoid duplicates on re-import
        self.logger.handlers.clear()

        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_format = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s — %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%SZ",
        )
        console_handler.setFormatter(console_format)
        self.logger.addHandler(console_handler)

        # File handler (optional)
        if log_path:
            log_path = Path(log_path)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(log_path, encoding="utf-8")
            file_handler.setLevel(logging.DEBUG)
            file_format = logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s — %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%SZ",
            )
            file_handler.setFormatter(file_format)
            self.logger.addHandler(file_handler)

    def info(self, msg: str) -> None:
        self.logger.info(msg)

    def warning(self, msg: str) -> None:
        self.logger.warning(msg)

    def error(self, msg: str) -> None:
        self.logger.error(msg)

    def debug(self, msg: str) -> None:
        self.logger.debug(msg)
