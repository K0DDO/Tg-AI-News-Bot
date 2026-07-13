"""Level 3 — Brief: presentation view-model of an Event (no DB table)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from sqlalchemy import inspect as sa_inspect

from app.models import Event
from app.utils.relative_dates import resolve_relative_dates
from app.utils.text_clean import strip_at_mentions
from app.utils.title_case import normalize_title


@dataclass(slots=True)
class BriefSource:
    channel_title: str
    channel_username: str | None
    url: str
    published_at: datetime | None
    author: str | None = None


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
    first_seen: datetime | None = None


class BriefBuilderService:
    def build(self, event: Event, *, lang: str = "ru", show_summary: bool = True) -> Brief:
        # Only use sources if already eager-loaded — never lazy-load (MissingGreenlet).
        loaded_sources = self._loaded_sources(event)
        sources_count = int(event.sources_count or 0) or len(loaded_sources)
        posts_count = int(event.posts_count or 0) or sources_count
        updated = bool(
            sources_count >= 2
            and event.updated_at
            and event.created_at
            and event.updated_at > event.created_at
        )
        sources: list[BriefSource] = []
        for src in loaded_sources:
            # Never touch src.message here — lazy load breaks async SQLAlchemy.
            sources.append(
                BriefSource(
                    channel_title=src.channel_title or "Channel",
                    channel_username=src.channel_username,
                    url=src.source_url,
                    published_at=src.created_at,
                    author=getattr(src, "author", None),
                )
            )
        ref = event.created_at
        if sources and sources[0].published_at:
            ref = sources[0].published_at
        first_seen = event.created_at
        for src in sources:
            if src.published_at and (first_seen is None or src.published_at < first_seen):
                first_seen = src.published_at
        title = normalize_title(
            strip_at_mentions(resolve_relative_dates(event.localized_title(lang), ref))
        )
        summary_raw = strip_at_mentions(
            resolve_relative_dates(event.localized_summary(lang), ref)
        )
        summary = summary_raw if show_summary else ""
        topic = resolve_relative_dates(event.topic or "", ref) or None
        if topic:
            topic = normalize_title(strip_at_mentions(topic))
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
            first_seen=first_seen,
        )

    @staticmethod
    def _loaded_sources(event: Event) -> list:
        """Return event.sources only when already in memory (no IO)."""
        try:
            insp = sa_inspect(event)
        except Exception:
            return []
        if "sources" in insp.unloaded:
            return []
        return list(event.sources or [])
