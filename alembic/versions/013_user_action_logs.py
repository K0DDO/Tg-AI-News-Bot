"""Add user_action_logs for per-user admin audit.

Revision ID: 013_user_action_logs
Revises: 012_digest_feed_ids
Create Date: 2026-07-16
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "013_user_action_logs"
down_revision: Union[str, None] = "012_digest_feed_ids"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_action_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("detail", sa.Text(), server_default="", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_action_logs_user_id", "user_action_logs", ["user_id"])
    op.create_index("ix_user_action_logs_telegram_id", "user_action_logs", ["telegram_id"])
    op.create_index("ix_user_action_logs_action", "user_action_logs", ["action"])
    op.create_index("ix_user_action_logs_created_at", "user_action_logs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_user_action_logs_created_at", table_name="user_action_logs")
    op.drop_index("ix_user_action_logs_action", table_name="user_action_logs")
    op.drop_index("ix_user_action_logs_telegram_id", table_name="user_action_logs")
    op.drop_index("ix_user_action_logs_user_id", table_name="user_action_logs")
    op.drop_table("user_action_logs")
