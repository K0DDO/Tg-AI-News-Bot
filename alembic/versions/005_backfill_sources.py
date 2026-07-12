"""Backfill sources_count on news.

Revision ID: 005_backfill_sources
Revises: 004_product
Create Date: 2026-07-12
"""

from typing import Sequence, Union

from alembic import op

revision: str = "005_backfill_sources"
down_revision: Union[str, None] = "004_product"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE news
        SET sources_count = (
            SELECT COUNT(*) FROM news_sources WHERE news_sources.news_id = news.id
        )
        """
    )


def downgrade() -> None:
    pass
