"""Process health / uptime for /status (in-memory, per container)."""

from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from typing import Deque

_STARTED_AT = datetime.now(timezone.utc)
_LAST_ERRORS: Deque[str] = deque(maxlen=8)
_LAST_INGEST: dict | None = None
_LAST_JOB_ERROR_AT: datetime | None = None


def started_at() -> datetime:
    return _STARTED_AT


def uptime_seconds() -> int:
    return int((datetime.now(timezone.utc) - _STARTED_AT).total_seconds())


def format_uptime() -> str:
    secs = uptime_seconds()
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m}m"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


def record_error(message: str) -> None:
    global _LAST_JOB_ERROR_AT
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    _LAST_ERRORS.appendleft(f"{ts}: {message[:200]}")
    _LAST_JOB_ERROR_AT = datetime.now(timezone.utc)


def record_ingest(stats: dict) -> None:
    global _LAST_INGEST
    _LAST_INGEST = dict(stats)


def last_errors(limit: int = 5) -> list[str]:
    return list(_LAST_ERRORS)[:limit]


def last_ingest() -> dict | None:
    return _LAST_INGEST
