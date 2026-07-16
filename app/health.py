"""In-memory process health, admin log ring, ingest stats."""

from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from typing import Any, Deque

_STARTED_AT = datetime.now(timezone.utc)
_LAST_ERRORS: Deque[str] = deque(maxlen=8)
_LAST_INGEST: dict | None = None
_LAST_JOB_ERROR_AT: datetime | None = None
# Admin "📜 Логи" — keep last 1000 important lines (not spam)
_ADMIN_LOG: Deque[dict] = deque(maxlen=1000)
_SCHEDULER_RUNNING = False
_JOB_LAST_RUN: dict[str, datetime] = {}
_COUNTERS: dict[str, int] = {"messages": 0, "errors": 0}


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


def set_scheduler_running(running: bool) -> None:
    global _SCHEDULER_RUNNING
    _SCHEDULER_RUNNING = bool(running)


def record_job_run(job_id: str) -> None:
    _JOB_LAST_RUN[job_id] = datetime.now(timezone.utc)


def last_job_run(job_id: str | None = None) -> datetime | None:
    if job_id:
        return _JOB_LAST_RUN.get(job_id)
    if not _JOB_LAST_RUN:
        return None
    return max(_JOB_LAST_RUN.values())


def bump_counter(name: str, delta: int = 1) -> None:
    _COUNTERS[name] = int(_COUNTERS.get(name, 0)) + int(delta)


def get_counter(name: str) -> int:
    return int(_COUNTERS.get(name, 0))


def record_error(message: str) -> None:
    global _LAST_JOB_ERROR_AT
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    short = message[:200]
    _LAST_ERRORS.appendleft(f"{ts}: {short}")
    _LAST_JOB_ERROR_AT = datetime.now(timezone.utc)
    bump_counter("errors")
    record_admin_log("ERROR", short)


def record_ingest(stats: dict) -> None:
    global _LAST_INGEST
    payload = dict(stats)
    payload.setdefault("at", datetime.now(timezone.utc).isoformat())
    _LAST_INGEST = payload
    created = int(payload.get("created_messages", 0) or 0)
    if created:
        bump_counter("messages", created)
    record_job_run("ingest")
    record_admin_log(
        "INFO",
        f"Ingest: +{payload.get('created_messages', 0)} msgs, "
        f"{payload.get('processed', 0)} processed, {payload.get('merged', 0)} merged",
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


def last_ingest_at() -> datetime | None:
    """UTC datetime of the last successful ingest cycle, if known."""
    if not _LAST_INGEST:
        return None
    raw = _LAST_INGEST.get("at")
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    if isinstance(raw, str) and raw.strip():
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def admin_logs(*, limit: int = 40, errors_only: bool = False) -> list[dict]:
    rows = list(_ADMIN_LOG)
    if errors_only:
        rows = [r for r in rows if r["level"] == "ERROR"]
    return rows[:limit]


def _ago_label(dt: datetime | None) -> str:
    if dt is None:
        return "—"
    secs = int((datetime.now(timezone.utc) - dt).total_seconds())
    if secs < 60:
        return f"{secs} сек назад"
    mins = secs // 60
    if mins < 60:
        return f"{mins} мин назад"
    hours = mins // 60
    if hours < 48:
        return f"{hours} ч назад"
    return dt.strftime("%d.%m %H:%M UTC")


def diagnostics_snapshot() -> dict[str, Any]:
    ingest = _LAST_INGEST or {}
    last_run = last_job_run() or last_ingest_at()
    return {
        "uptime": format_uptime(),
        "started_at": _STARTED_AT.strftime("%Y-%m-%d %H:%M UTC"),
        "last_ingest": ingest,
        "last_errors": last_errors(3),
        "scheduler": "ok" if _SCHEDULER_RUNNING else "stopped",
        "scheduler_running": _SCHEDULER_RUNNING,
        "last_job_run": last_run,
        "last_job_ago": _ago_label(last_run),
        "messages_total": get_counter("messages"),
        "errors_total": get_counter("errors"),
        "job_runs": {k: v.isoformat() for k, v in _JOB_LAST_RUN.items()},
    }
