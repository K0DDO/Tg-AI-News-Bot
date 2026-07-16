"""Extend ai_usage_logs + processing_jobs + backfill stage fields.

Revision ID: 016_ai_scale
Revises: 015_whitelist_orphans
Create Date: 2026-07-17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "016_ai_scale"
down_revision: Union[str, None] = "015_whitelist_orphans"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("ai_usage_logs", sa.Column("model", sa.String(length=128), nullable=True))
    op.add_column("ai_usage_logs", sa.Column("key_fingerprint", sa.String(length=32), nullable=True))
    op.add_column("ai_usage_logs", sa.Column("latency_ms", sa.Integer(), nullable=True))
    op.add_column(
        "ai_usage_logs",
        sa.Column("status", sa.String(length=32), server_default="ok", nullable=False),
    )
    op.add_column("ai_usage_logs", sa.Column("error_code", sa.String(length=64), nullable=True))
    op.create_index("ix_ai_usage_logs_key_fingerprint", "ai_usage_logs", ["key_fingerprint"])

    op.add_column(
        "backfill_jobs",
        sa.Column("current_stage", sa.String(length=32), server_default="queued", nullable=False),
    )
    op.add_column(
        "backfill_jobs",
        sa.Column("total_tasks", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "backfill_jobs",
        sa.Column("completed_tasks", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "backfill_jobs",
        sa.Column("failed_tasks", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "backfill_jobs",
        sa.Column("messages_total", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "backfill_jobs",
        sa.Column("events_created", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "backfill_jobs",
        sa.Column("events_merged", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column("backfill_jobs", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("backfill_jobs", sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "processing_jobs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("job_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="queued", nullable=False),
        sa.Column("current_stage", sa.String(length=32), server_default="queued", nullable=False),
        sa.Column("priority", sa.Integer(), server_default="100", nullable=False),
        sa.Column("channel_id", sa.Integer(), nullable=True),
        sa.Column("backfill_job_id", sa.Integer(), nullable=True),
        sa.Column("message_ids", sa.JSON(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("total_tasks", sa.Integer(), server_default="0", nullable=False),
        sa.Column("completed_tasks", sa.Integer(), server_default="0", nullable=False),
        sa.Column("failed_tasks", sa.Integer(), server_default="0", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default="5", nullable=False),
        sa.Column("last_error", sa.Text(), server_default="", nullable=False),
        sa.Column("run_after", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["channel_id"], ["channels.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["backfill_job_id"], ["backfill_jobs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_processing_jobs_status", "processing_jobs", ["status"])
    op.create_index("ix_processing_jobs_job_type", "processing_jobs", ["job_type"])
    op.create_index("ix_processing_jobs_run_after", "processing_jobs", ["run_after"])
    op.create_index("ix_processing_jobs_channel_id", "processing_jobs", ["channel_id"])


def downgrade() -> None:
    op.drop_index("ix_processing_jobs_channel_id", table_name="processing_jobs")
    op.drop_index("ix_processing_jobs_run_after", table_name="processing_jobs")
    op.drop_index("ix_processing_jobs_job_type", table_name="processing_jobs")
    op.drop_index("ix_processing_jobs_status", table_name="processing_jobs")
    op.drop_table("processing_jobs")

    op.drop_column("backfill_jobs", "finished_at")
    op.drop_column("backfill_jobs", "started_at")
    op.drop_column("backfill_jobs", "events_merged")
    op.drop_column("backfill_jobs", "events_created")
    op.drop_column("backfill_jobs", "messages_total")
    op.drop_column("backfill_jobs", "failed_tasks")
    op.drop_column("backfill_jobs", "completed_tasks")
    op.drop_column("backfill_jobs", "total_tasks")
    op.drop_column("backfill_jobs", "current_stage")

    op.drop_index("ix_ai_usage_logs_key_fingerprint", table_name="ai_usage_logs")
    op.drop_column("ai_usage_logs", "error_code")
    op.drop_column("ai_usage_logs", "status")
    op.drop_column("ai_usage_logs", "latency_ms")
    op.drop_column("ai_usage_logs", "key_fingerprint")
    op.drop_column("ai_usage_logs", "model")
