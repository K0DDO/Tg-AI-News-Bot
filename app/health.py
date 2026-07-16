"""In-memory process health, admin log ring, ingest stats."""

from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from typing import Deque

_STARTED_AT = datetime.now(timezone.utc)
_LAST_ERRORS: Deque[str] = deque(maxlen=8)
_LAST_INGEST: dict | None = None
_LAST_JOB_ERROR_AT: datetime | None = None
# Admin "📜 Логи" — keep last 1000 important lines (not spam)
_ADMIN_LOG: Deque[dict] = deque(maxlen=1000)


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
    short = message[:200]
    _LAST_ERRORS.appendleft(f"{ts}: {short}")
    _LAST_JOB_ERROR_AT = datetime.now(timezone.utc)
    record_admin_log("ERROR", short)


def record_ingest(stats: dict) -> None:
    global _LAST_INGEST
    _LAST_INGEST = dict(stats)
    record_admin_log(
        "INFO",
        f"Ingest: +{stats.get('created_messages', 0)} msgs, "
        f"{stats.get('processed', 0)} processed, {stats.get('merged', 0)} merged",
    )


def record_admin_log(level: str, message: str) -> None:
    """Store important events for the admin Logs screen."""
    level = (level or "INFO").upper()
    if level not in {"ERROR", "WARNING", "INFO"}:
        level = "INFO"
    _ADMIN_LOG.appendleft(
        {
            "ts": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            "level": level,
            "message": (message or "")[:240],
        }
    )


def last_errors(limit: int = 5) -> list[str]:
    return list(_LAST_ERRORS)[:limit]


def last_ingest() -> dict | None:
    return _LAST_INGEST


def admin_logs(*, limit: int = 40, errors_only: bool = False) -> list[dict]:
    rows = list(_ADMIN_LOG)
    if errors_only:
        rows = [r for r in rows if r["level"] == "ERROR"]
    return rows[:limit]


def diagnostics_snapshot() -> dict:
    ingest = _LAST_INGEST or {}
    return {
        "uptime": format_uptime(),
        "started_at": _STARTED_AT.strftime("%Y-%m-%d %H:%M UTC"),
        "last_ingest": ingest,
        "last_errors": last_errors(3),
        "scheduler": "ok",
    }
