"""Add backfill_jobs for user-visible load progress.

Revision ID: 009_backfill_jobs
Revises: 008_backfill
Create Date: 2026-07-13
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "009_backfill_jobs"
down_revision: Union[str, None] = "008_backfill"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "backfill_jobs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("days", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="queued", nullable=False),
        sa.Column("channel_ids", sa.JSON(), nullable=False),
        sa.Column("done_channel_ids", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("messages_fetched", sa.Integer(), server_default="0", nullable=False),
        sa.Column("events_processed", sa.Integer(), server_default="0", nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=True),
        sa.Column("message_id", sa.Integer(), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_backfill_jobs_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_backfill_jobs")),
    )
    op.create_index(op.f("ix_backfill_jobs_user_id"), "backfill_jobs", ["user_id"], unique=False)
    op.create_index(op.f("ix_backfill_jobs_status"), "backfill_jobs", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_backfill_jobs_status"), table_name="backfill_jobs")
    op.drop_index(op.f("ix_backfill_jobs_user_id"), table_name="backfill_jobs")
    op.drop_table("backfill_jobs")
