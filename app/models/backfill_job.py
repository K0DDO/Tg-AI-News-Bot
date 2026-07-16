"""User-scoped channel history backfill jobs with progress."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base

# Weighted stages for real progress (sum = 100)
_STAGE_WEIGHTS = {
    "queued": 0,
    "connect": 5,
    "fetch": 25,
    "clean": 10,
    "dedupe": 5,
    "ai": 40,
    "relations": 10,
    "save": 5,
    "done": 100,
}

_STAGE_ORDER = (
    "queued",
    "connect",
    "fetch",
    "clean",
    "dedupe",
    "ai",
    "relations",
    "save",
    "done",
)


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
    current_stage: Mapped[str] = mapped_column(
        String(32), default="queued", server_default="queued", nullable=False
    )
    total_tasks: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    completed_tasks: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    failed_tasks: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    messages_total: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    events_created: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    events_merged: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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
        """Real stage-weighted progress (not fake 0→92→100)."""
        if self.status == "done" or self.current_stage == "done":
            return 100
        stage = (self.current_stage or self.status or "queued").lower()
        # Map legacy statuses
        if stage == "running":
            stage = "fetch"
        if stage == "analyzing":
            stage = "ai"

        base = 0
        for s in _STAGE_ORDER:
            if s == stage:
                break
            if s in {"queued", "done"}:
                continue
            base += _STAGE_WEIGHTS.get(s, 0)

        weight = _STAGE_WEIGHTS.get(stage, 10)
        # Within-stage progress from completed_tasks / total_tasks
        total_t = int(self.total_tasks or 0)
        done_t = int(self.completed_tasks or 0)
        if total_t > 0:
            frac = min(1.0, max(0.0, done_t / total_t))
        elif stage == "fetch" and self.total > 0:
            frac = min(1.0, max(0.0, self.done / self.total))
        else:
            frac = 0.0
        pct = int(base + weight * frac)
        return max(0, min(99, pct))

    @property
    def stage_label_key(self) -> str:
        stage = (self.current_stage or self.status or "queued").lower()
        if stage == "running":
            stage = "fetch"
        if stage == "analyzing":
            stage = "ai"
        return {
            "queued": "bf_stage_queued",
            "connect": "bf_stage_connect",
            "fetch": "bf_stage_fetch",
            "clean": "bf_stage_clean",
            "dedupe": "bf_stage_dedupe",
            "ai": "bf_stage_ai",
            "relations": "bf_stage_relations",
            "save": "bf_stage_save",
            "done": "bf_stage_done",
        }.get(stage, "bf_stage_queued")
