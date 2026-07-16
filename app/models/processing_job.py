"""Durable processing queue for AI batches and maintenance tasks."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class ProcessingJob(Base):
    __tablename__ = "processing_jobs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    job_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # ai_batch | kg_maintenance | news_repair | nightly
    status: Mapped[str] = mapped_column(
        String(32), default="queued", server_default="queued", nullable=False, index=True
    )
    current_stage: Mapped[str] = mapped_column(
        String(32), default="queued", server_default="queued", nullable=False
    )
    priority: Mapped[int] = mapped_column(Integer, default=100, server_default="100", nullable=False)
    channel_id: Mapped[int | None] = mapped_column(
        ForeignKey("channels.id", ondelete="SET NULL"), nullable=True, index=True
    )
    backfill_job_id: Mapped[int | None] = mapped_column(
        ForeignKey("backfill_jobs.id", ondelete="SET NULL"), nullable=True
    )
    message_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    total_tasks: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    completed_tasks: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    failed_tasks: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5, server_default="5", nullable=False)
    last_error: Mapped[str] = mapped_column(Text, default="", server_default="", nullable=False)
    run_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    @property
    def percent(self) -> int:
        if self.status == "done":
            return 100
        if self.status == "failed":
            return max(0, min(99, int(100 * self.completed_tasks / max(1, self.total_tasks))))
        if self.total_tasks <= 0:
            return 0
        return max(0, min(99, int(100 * self.completed_tasks / self.total_tasks)))
