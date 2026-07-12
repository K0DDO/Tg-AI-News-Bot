"""User preferences and per-user news read state (UX / personalization)."""

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
from sqlalchemy.orm import Mapped, mapped_column, relationship

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
    update_interval_minutes: Mapped[int] = mapped_column(Integer, default=60, server_default="60", nullable=False)
    min_importance: Mapped[float] = mapped_column(Float, default=0.0, server_default="0", nullable=False)
    enabled_categories: Mapped[list | None] = mapped_column(JSON, nullable=True)
    ignored_topics: Mapped[str] = mapped_column(Text, default="", server_default="", nullable=False)
    digest_chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    digest_message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
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


class UserNewsState(Base):
    """Tracks read/hidden news per user for the personalized feed."""

    __tablename__ = "user_news_states"
    __table_args__ = (
        UniqueConstraint("user_id", "news_id", name="uq_user_news_states_user_id_news_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    news_id: Mapped[int] = mapped_column(ForeignKey("news.id", ondelete="CASCADE"), nullable=False, index=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    is_hidden: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    score_at_interaction: Mapped[Decimal] = mapped_column(
        Numeric(4, 2),
        default=Decimal("0"),
        server_default="0",
        nullable=False,
    )
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
