"""Store last pushed feed event ids for in-place digest updates.

Revision ID: 012_digest_feed_ids
Revises: 011_product_upgrade
Create Date: 2026-07-16
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "012_digest_feed_ids"
down_revision: Union[str, None] = "011_product_upgrade"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "user_settings",
        sa.Column("digest_feed_ids", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("user_settings", "digest_feed_ids")
