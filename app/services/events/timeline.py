"""Timeline helpers for Event evolution history."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def make_entry(
    *,
    kind: str,
    text: str,
    sources: int | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "kind": kind,
        "text": text,
    }
    if sources is not None:
        entry["sources"] = sources
    if extra:
        entry.update(extra)
    return entry


class TimelineService:
    def append(self, timeline: list | None, entry: dict[str, Any], *, limit: int = 40) -> list:
        items = list(timeline or [])
        items.append(entry)
        return items[-limit:]
