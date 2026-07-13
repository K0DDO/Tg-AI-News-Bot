"""Level 1 — TelegramPost (raw Telegram message as data source only)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.models.enums import MessageStatus


class Message(Base):
    """Raw Telegram message. Users never interact with this directly."""

    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint(
            "channel_id",
            "telegram_message_id",
            name="uq_messages_channel_id_telegram_message_id",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    channel_id: Mapped[int] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    telegram_message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(32),
        default=MessageStatus.RAW.value,
        server_default=MessageStatus.RAW.value,
        nullable=False,
        index=True,
    )
    filter_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    language: Mapped[str | None] = mapped_column(String(16), nullable=True)
    is_news: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    is_advertisement: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    raw_embedding: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    media: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    raw_entities: Mapped[list | None] = mapped_column(JSON, nullable=True)
    author: Mapped[str | None] = mapped_column(String(255), nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    channel = relationship("Channel", back_populates="messages")
    event_sources = relationship("EventSource", back_populates="message")

    # compat
    @property
    def news_sources(self):
        return self.event_sources

    @property
    def original_text(self) -> str:
        return self.text

    @property
    def original_url(self) -> str:
        return self.url

    def __repr__(self) -> str:
        return f"<TelegramPost id={self.id} channel_id={self.channel_id} status={self.status}>"


# Domain alias — Level 1 name from architecture
TelegramPost = Message
