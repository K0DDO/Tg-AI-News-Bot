"""Level 2 — Event (canonical information event) + EventSource evidence links."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, synonym

from app.database.base import Base


class Event(Base):
    """One concrete news event; aggregates many Telegram posts."""

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    category: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    # Full event sentence, NOT a single word
    topic: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    why_important: Mapped[str | None] = mapped_column(Text, nullable=True)
    entities: Mapped[list | None] = mapped_column(JSON, nullable=True)
    keywords: Mapped[list | None] = mapped_column(JSON, nullable=True)
    importance_score: Mapped[Decimal] = mapped_column(
        Numeric(4, 2),
        default=Decimal("0"),
        server_default="0",
        nullable=False,
        index=True,
    )
    embedding: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(
        String(32),
        default="active",
        server_default="active",
        nullable=False,
        index=True,
    )
    timeline: Mapped[list | None] = mapped_column(JSON, nullable=True)
    sources_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    posts_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    ai_reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    related_event_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    title_i18n: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    summary_i18n: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    sources = relationship(
        "EventSource",
        back_populates="event",
        cascade="all, delete-orphan",
    )
    reactions = relationship(
        "Reaction",
        back_populates="event",
        cascade="all, delete-orphan",
    )

    def localized_title(self, lang: str) -> str:
        if lang and self.title_i18n and lang in self.title_i18n:
            return str(self.title_i18n[lang])
        return self.title

    def localized_summary(self, lang: str) -> str:
        if lang and self.summary_i18n and lang in self.summary_i18n:
            return str(self.summary_i18n[lang])
        return self.summary

    def __repr__(self) -> str:
        return f"<Event id={self.id} title={self.title[:40]!r} score={self.importance_score}>"


class EventSource(Base):
    __tablename__ = "event_sources"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    message_id: Mapped[int | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    channel_title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    channel_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    author: Mapped[str | None] = mapped_column(String(255), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    event = relationship("Event", back_populates="sources")
    message = relationship("Message", back_populates="event_sources")

    # compat aliases
    news_id = synonym("event_id")
    news = synonym("event")


# Compat aliases for one release
News = Event
NewsSource = EventSource
