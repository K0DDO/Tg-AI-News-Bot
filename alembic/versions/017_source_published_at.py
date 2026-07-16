"""Add published_at to event_sources (real Telegram publish time).

Revision ID: 017_source_published_at
Revises: 016_ai_scale
Create Date: 2026-07-17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "017_source_published_at"
down_revision: Union[str, None] = "016_ai_scale"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "event_sources",
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_event_sources_published_at", "event_sources", ["published_at"])
    # Backfill from linked messages when possible
    op.execute(
        """
        UPDATE event_sources AS es
        SET published_at = m.published_at
        FROM messages AS m
        WHERE es.message_id = m.id
          AND es.published_at IS NULL
        """
    )
    op.execute(
        """
        UPDATE event_sources
        SET published_at = created_at
        WHERE published_at IS NULL
        """
    )


def downgrade() -> None:
    op.drop_index("ix_event_sources_published_at", table_name="event_sources")
    op.drop_column("event_sources", "published_at")
