"""Add pending_backfill_days to channels for history load jobs.

Revision ID: 008_backfill
Revises: 007_multiuser
Create Date: 2026-07-13
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "008_backfill"
down_revision: Union[str, None] = "007_multiuser"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "channels",
        sa.Column("pending_backfill_days", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("channels", "pending_backfill_days")
