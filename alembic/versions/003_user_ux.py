"""Add user_settings and user_news_states for UX personalization.

Revision ID: 003_user_ux
Revises: 002_ai_fields
Create Date: 2026-07-12
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003_user_ux"
down_revision: Union[str, None] = "002_ai_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_settings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("welcome_seen", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("update_interval_minutes", sa.Integer(), server_default="60", nullable=False),
        sa.Column("min_importance", sa.Float(), server_default="0", nullable=False),
        sa.Column("enabled_categories", sa.JSON(), nullable=True),
        sa.Column("ignored_topics", sa.Text(), server_default="", nullable=False),
        sa.Column("digest_chat_id", sa.BigInteger(), nullable=True),
        sa.Column("digest_message_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_settings")),
        sa.UniqueConstraint("user_id", name=op.f("uq_user_settings_user_id")),
    )
    op.create_index(op.f("ix_user_settings_user_id"), "user_settings", ["user_id"], unique=False)

    op.create_table(
        "user_news_states",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("news_id", sa.Integer(), nullable=False),
        sa.Column("is_read", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("is_hidden", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("score_at_interaction", sa.Numeric(4, 2), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["news_id"], ["news.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_news_states")),
        sa.UniqueConstraint("user_id", "news_id", name="uq_user_news_states_user_id_news_id"),
    )
    op.create_index(op.f("ix_user_news_states_user_id"), "user_news_states", ["user_id"], unique=False)
    op.create_index(op.f("ix_user_news_states_news_id"), "user_news_states", ["news_id"], unique=False)


def downgrade() -> None:
    op.drop_table("user_news_states")
    op.drop_table("user_settings")
