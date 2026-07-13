"""Level 3 — Brief: presentation view-model of an Event (no DB table)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from app.models import Event
from app.utils.relative_dates import resolve_relative_dates


@dataclass(slots=True)
class BriefSource:
    channel_title: str
    channel_username: str | None
    url: str
    published_at: datetime | None


@dataclass(slots=True)
class Brief:
    """User-facing card built from Event. Users only see Briefs."""

    event_id: int
    title: str
    summary: str
    category: str
    topic: str | None
    importance_score: float
    sources_count: int
    posts_count: int
    updated: bool
    why_important: str | None
    entities: list[str] = field(default_factory=list)
    timeline: list[dict] = field(default_factory=list)
    sources: list[BriefSource] = field(default_factory=list)
    lang: str = "ru"


class BriefBuilderService:
    def build(self, event: Event, *, lang: str = "ru") -> Brief:
        sources_count = event.sources_count or len(event.sources or [])
        posts_count = event.posts_count or sources_count
        updated = bool(
            sources_count >= 2
            and event.updated_at
            and event.created_at
            and event.updated_at > event.created_at
        )
        sources: list[BriefSource] = []
        for src in event.sources or []:
            # Never touch src.message here — lazy load breaks async SQLAlchemy (MissingGreenlet).
            sources.append(
                BriefSource(
                    channel_title=src.channel_title or "Channel",
                    channel_username=src.channel_username,
                    url=src.source_url,
                    published_at=src.created_at,
                )
            )
        ref = event.created_at
        if sources and sources[0].published_at:
            ref = sources[0].published_at
        title = resolve_relative_dates(event.localized_title(lang), ref)
        summary = resolve_relative_dates(event.localized_summary(lang), ref)
        topic = resolve_relative_dates(event.topic or "", ref) or None
        return Brief(
            event_id=event.id,
            title=title,
            summary=summary,
            category=event.category or "Other",
            topic=topic,
            importance_score=float(event.importance_score or Decimal("0")),
            sources_count=sources_count,
            posts_count=posts_count,
            updated=updated,
            why_important=event.why_important,
            entities=list(event.entities or []),
            timeline=list(event.timeline or []),
            sources=sources,
            lang=lang,
        )
