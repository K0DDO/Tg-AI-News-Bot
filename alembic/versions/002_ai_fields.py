"""Add news.embedding and ai_usage_logs.

Revision ID: 002_ai_fields
Revises: 001_initial
Create Date: 2026-07-11
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002_ai_fields"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("news", sa.Column("embedding", sa.JSON(), nullable=True))
    op.create_table(
        "ai_usage_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("operation", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_usage_logs")),
    )
    op.create_index(op.f("ix_ai_usage_logs_provider"), "ai_usage_logs", ["provider"], unique=False)
    op.create_index(op.f("ix_ai_usage_logs_operation"), "ai_usage_logs", ["operation"], unique=False)
    op.create_index(op.f("ix_ai_usage_logs_created_at"), "ai_usage_logs", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_table("ai_usage_logs")
    op.drop_column("news", "embedding")
