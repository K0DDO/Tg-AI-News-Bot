"""Product polish schema: topics, i18n, favorites, why_important.

Revision ID: 004_product
Revises: 003_user_ux
Create Date: 2026-07-12
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004_product"
down_revision: Union[str, None] = "003_user_ux"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("news", sa.Column("topic", sa.String(length=128), nullable=True))
    op.add_column("news", sa.Column("why_important", sa.Text(), nullable=True))
    op.add_column("news", sa.Column("sources_count", sa.Integer(), server_default="0", nullable=False))
    op.add_column("news", sa.Column("title_i18n", sa.JSON(), nullable=True))
    op.add_column("news", sa.Column("summary_i18n", sa.JSON(), nullable=True))
    op.create_index(op.f("ix_news_topic"), "news", ["topic"], unique=False)

    op.add_column("news_sources", sa.Column("channel_username", sa.String(length=255), nullable=True))

    op.add_column("user_settings", sa.Column("language", sa.String(length=8), server_default="ru", nullable=False))
    op.add_column(
        "user_settings",
        sa.Column("language_chosen", sa.Boolean(), server_default="false", nullable=False),
    )

    op.add_column(
        "user_news_states",
        sa.Column("is_favorite", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column(
        "user_news_states",
        sa.Column("sources_at_interaction", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column("user_news_states", sa.Column("read_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("user_news_states", sa.Column("favorited_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("user_news_states", "favorited_at")
    op.drop_column("user_news_states", "read_at")
    op.drop_column("user_news_states", "sources_at_interaction")
    op.drop_column("user_news_states", "is_favorite")
    op.drop_column("user_settings", "language_chosen")
    op.drop_column("user_settings", "language")
    op.drop_column("news_sources", "channel_username")
    op.drop_index(op.f("ix_news_topic"), table_name="news")
    op.drop_column("news", "summary_i18n")
    op.drop_column("news", "title_i18n")
    op.drop_column("news", "sources_count")
    op.drop_column("news", "why_important")
    op.drop_column("news", "topic")
