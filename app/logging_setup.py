"""Rotating file logs for production (bot/parser/search/graph/scheduler/errors)."""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

_LOG_FILES = {
    "briefly.runtime": "bot.log",
    "app.bot": "bot.log",
    "app.tasks": "scheduler.log",
    "app.tasks.pipeline": "parser.log",
    "app.services.search": "search.log",
    "app.services.knowledge": "graph.log",
}


def setup_logging(level: str = "INFO", logs_dir: str | None = None) -> None:
    root = logging.getLogger()
    if getattr(root, "_briefly_configured", False):
        return

    log_level = getattr(logging, (level or "INFO").upper(), logging.INFO)
    root.setLevel(log_level)

    fmt = logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    console.setLevel(log_level)
    root.addHandler(console)

    base = Path(logs_dir or os.getenv("LOGS_DIR", "/app/logs"))
    try:
        base.mkdir(parents=True, exist_ok=True)
        writable = os.access(base, os.W_OK)
    except OSError:
        writable = False

    if writable:
        # Shared error file for WARNING+
        err = RotatingFileHandler(
            base / "errors.log",
            maxBytes=5 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        err.setLevel(logging.WARNING)
        err.setFormatter(fmt)
        root.addHandler(err)

        # Named rotating logs (avoid duplicate handlers per process)
        created: dict[str, RotatingFileHandler] = {}
        for logger_name, filename in _LOG_FILES.items():
            if filename not in created:
                handler = RotatingFileHandler(
                    base / filename,
                    maxBytes=5 * 1024 * 1024,
                    backupCount=7,
                    encoding="utf-8",
                )
                handler.setFormatter(fmt)
                handler.setLevel(log_level)
                created[filename] = handler
            logging.getLogger(logger_name).addHandler(created[filename])
            logging.getLogger(logger_name).propagate = True

    root._briefly_configured = True  # type: ignore[attr-defined]
