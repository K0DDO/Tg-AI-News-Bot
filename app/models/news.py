from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class News(Base):
    """Aggregated / clustered news item shown in digests."""

    __tablename__ = "news"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    category: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    importance_score: Mapped[Decimal] = mapped_column(
        Numeric(4, 2),
        default=Decimal("0"),
        server_default="0",
        nullable=False,
        index=True,
    )
    embedding: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
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
        "NewsSource",
        back_populates="news",
        cascade="all, delete-orphan",
    )
    reactions = relationship(
        "Reaction",
        back_populates="news",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<News id={self.id} title={self.title[:40]!r} score={self.importance_score}>"


class NewsSource(Base):
    """
    Link between a News cluster and an original Message.

    source_url / channel_title are denormalized so cleanup can delete
    old Message rows without breaking digest "Sources" links.
    """

    __tablename__ = "news_sources"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    news_id: Mapped[int] = mapped_column(
        ForeignKey("news.id", ondelete="CASCADE"),
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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    news = relationship("News", back_populates="sources")
    message = relationship("Message", back_populates="news_sources")
