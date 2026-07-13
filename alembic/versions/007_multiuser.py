"""Multi-user: last_seen, settings, UserEventState personal fields.

Revision ID: 007_multiuser
Revises: 006_events
Create Date: 2026-07-13
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "007_multiuser"
down_revision: Union[str, None] = "006_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True))

    op.add_column(
        "user_settings",
        sa.Column("news_language", sa.String(length=8), server_default="ru", nullable=False),
    )
    op.add_column(
        "user_settings",
        sa.Column("feed_page_size", sa.Integer(), server_default="5", nullable=False),
    )
    op.add_column(
        "user_settings",
        sa.Column("notifications_enabled", sa.Boolean(), server_default="true", nullable=False),
    )
    op.add_column(
        "user_settings",
        sa.Column("include_external_news", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column(
        "user_settings",
        sa.Column("show_summary", sa.Boolean(), server_default="true", nullable=False),
    )
    op.add_column(
        "user_settings",
        sa.Column("tutorial_seen", sa.Boolean(), server_default="false", nullable=False),
    )

    op.add_column(
        "user_event_states",
        sa.Column("is_shown", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column(
        "user_event_states",
        sa.Column("shown_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "user_event_states",
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "user_event_states",
        sa.Column("is_liked", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column(
        "user_event_states",
        sa.Column("is_disliked", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column(
        "user_event_states",
        sa.Column(
            "personal_score",
            sa.Numeric(precision=6, scale=2),
            server_default="0",
            nullable=False,
        ),
    )

    op.add_column("messages", sa.Column("author", sa.String(length=255), nullable=True))
    op.add_column("event_sources", sa.Column("author", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("event_sources", "author")
    op.drop_column("messages", "author")
    op.drop_column("user_event_states", "personal_score")
    op.drop_column("user_event_states", "is_disliked")
    op.drop_column("user_event_states", "is_liked")
    op.drop_column("user_event_states", "opened_at")
    op.drop_column("user_event_states", "shown_count")
    op.drop_column("user_event_states", "is_shown")
    op.drop_column("user_settings", "tutorial_seen")
    op.drop_column("user_settings", "show_summary")
    op.drop_column("user_settings", "include_external_news")
    op.drop_column("user_settings", "notifications_enabled")
    op.drop_column("user_settings", "feed_page_size")
    op.drop_column("user_settings", "news_language")
    op.drop_column("users", "last_seen_at")
