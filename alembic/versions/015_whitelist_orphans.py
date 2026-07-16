"""Orphan channel cleanup helpers + whitelist tables.

Revision ID: 015_whitelist_orphans
Revises: 014_ui_screen_message
Create Date: 2026-07-16
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "015_whitelist_orphans"
down_revision: Union[str, None] = "014_ui_screen_message"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "bot_settings",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("value", sa.Text(), server_default="", nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("key"),
    )
    op.create_table(
        "whitelist_entries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("note", sa.String(length=255), server_default="", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("telegram_id", name="uq_whitelist_entries_telegram_id"),
    )
    op.create_index("ix_whitelist_entries_telegram_id", "whitelist_entries", ["telegram_id"])
    # Default: whitelist OFF (open bot) until admin enables it
    op.execute(
        "INSERT INTO bot_settings (key, value) VALUES ('whitelist_enabled', '0')"
    )


def downgrade() -> None:
    op.drop_index("ix_whitelist_entries_telegram_id", table_name="whitelist_entries")
    op.drop_table("whitelist_entries")
    op.drop_table("bot_settings")
