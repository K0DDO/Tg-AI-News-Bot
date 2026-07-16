"""Track last interactive UI message per user.

Revision ID: 014_ui_screen_message
Revises: 013_user_action_logs
Create Date: 2026-07-16
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "014_ui_screen_message"
down_revision: Union[str, None] = "013_user_action_logs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("user_settings", sa.Column("ui_chat_id", sa.BigInteger(), nullable=True))
    op.add_column("user_settings", sa.Column("ui_message_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("user_settings", "ui_message_id")
    op.drop_column("user_settings", "ui_chat_id")
