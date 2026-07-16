"""User preferences and per-user event read state."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, synonym

from app.database.base import Base


class UserSettings(Base):
    __tablename__ = "user_settings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    welcome_seen: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    tutorial_seen: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    language: Mapped[str] = mapped_column(String(8), default="ru", server_default="ru", nullable=False)
    language_chosen: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    news_language: Mapped[str] = mapped_column(String(8), default="ru", server_default="ru", nullable=False)
    feed_page_size: Mapped[int] = mapped_column(Integer, default=5, server_default="5", nullable=False)
    notifications_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False
    )
    include_external_news: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    show_summary: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    update_interval_minutes: Mapped[int] = mapped_column(Integer, default=60, server_default="60", nullable=False)
    min_importance: Mapped[float] = mapped_column(Float, default=0.0, server_default="0", nullable=False)
    enabled_categories: Mapped[list | None] = mapped_column(JSON, nullable=True)
    ignored_topics: Mapped[str] = mapped_column(Text, default="", server_default="", nullable=False)
    digest_chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    digest_message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    digest_feed_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # Product upgrade fields
    timezone: Mapped[str] = mapped_column(
        String(64), default="Europe/Moscow", server_default="Europe/Moscow", nullable=False
    )
    theme_weights: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    digest_mode: Mapped[str] = mapped_column(
        String(16), default="1h", server_default="1h", nullable=False
    )  # off | 1h | 3h | 6h | daily
    digest_time: Mapped[str] = mapped_column(
        String(8), default="09:00", server_default="09:00", nullable=False
    )
    dnd_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    dnd_weekday_start: Mapped[str] = mapped_column(
        String(8), default="23:00", server_default="23:00", nullable=False
    )
    dnd_weekday_end: Mapped[str] = mapped_column(
        String(8), default="08:00", server_default="08:00", nullable=False
    )
    dnd_weekend_start: Mapped[str] = mapped_column(
        String(8), default="00:00", server_default="00:00", nullable=False
    )
    dnd_weekend_end: Mapped[str] = mapped_column(
        String(8), default="10:00", server_default="10:00", nullable=False
    )
    last_digest_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user = relationship("User", back_populates="settings")


class UserEventState(Base):
    """Per-user link to a shared Event (also known as UserEvent)."""

    __tablename__ = "user_event_states"
    __table_args__ = (
        UniqueConstraint("user_id", "event_id", name="uq_user_event_states_user_id_event_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    is_hidden: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    is_favorite: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    is_shown: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    shown_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    is_liked: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    is_disliked: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    personal_score: Mapped[Decimal] = mapped_column(
        Numeric(6, 2),
        default=Decimal("0"),
        server_default="0",
        nullable=False,
    )
    score_at_interaction: Mapped[Decimal] = mapped_column(
        Numeric(4, 2),
        default=Decimal("0"),
        server_default="0",
        nullable=False,
    )
    sources_at_interaction: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    favorited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    news_id = synonym("event_id")


UserNewsState = UserEventState
UserEvent = UserEventState
