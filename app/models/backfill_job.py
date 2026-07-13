"""User-scoped channel history backfill jobs with progress."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class BackfillJob(Base):
    __tablename__ = "backfill_jobs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    days: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        default="queued",
        server_default="queued",
        nullable=False,
        index=True,
    )
    channel_ids: Mapped[list] = mapped_column(JSON, nullable=False)
    done_channel_ids: Mapped[list] = mapped_column(JSON, default=list, server_default="[]", nullable=False)
    messages_fetched: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    events_processed: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
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

    user = relationship("User")

    @property
    def total(self) -> int:
        return len(self.channel_ids or [])

    @property
    def done(self) -> int:
        return len(self.done_channel_ids or [])

    @property
    def percent(self) -> int:
        total = self.total
        if total <= 0:
            return 100 if self.status == "done" else 0
        base = int(self.done * 90 / total)
        if self.status == "done":
            return 100
        if self.status == "analyzing":
            return min(99, max(base, 92))
        return min(90, base)
