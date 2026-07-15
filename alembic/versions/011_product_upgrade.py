"""Add product upgrade: ban, admin accounts, digest/DND/TZ, AI tokens.

Revision ID: 011_product_upgrade
Revises: 010_knowledge_graph
Create Date: 2026-07-15
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "011_product_upgrade"
down_revision: Union[str, None] = "010_knowledge_graph"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_banned", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column("users", sa.Column("banned_at", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "admin_accounts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        sa.Column("must_set_password", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_admin_accounts")),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index(op.f("ix_admin_accounts_user_id"), "admin_accounts", ["user_id"], unique=False)
    op.create_index(op.f("ix_admin_accounts_role"), "admin_accounts", ["role"], unique=False)

    op.add_column(
        "user_settings",
        sa.Column("timezone", sa.String(length=64), server_default="Europe/Moscow", nullable=False),
    )
    op.add_column("user_settings", sa.Column("theme_weights", sa.JSON(), nullable=True))
    op.add_column(
        "user_settings",
        sa.Column("digest_mode", sa.String(length=16), server_default="1h", nullable=False),
    )
    op.add_column(
        "user_settings",
        sa.Column("digest_time", sa.String(length=8), server_default="09:00", nullable=False),
    )
    op.add_column(
        "user_settings",
        sa.Column("dnd_enabled", sa.Boolean(), server_default="true", nullable=False),
    )
    op.add_column(
        "user_settings",
        sa.Column("dnd_weekday_start", sa.String(length=8), server_default="23:00", nullable=False),
    )
    op.add_column(
        "user_settings",
        sa.Column("dnd_weekday_end", sa.String(length=8), server_default="08:00", nullable=False),
    )
    op.add_column(
        "user_settings",
        sa.Column("dnd_weekend_start", sa.String(length=8), server_default="00:00", nullable=False),
    )
    op.add_column(
        "user_settings",
        sa.Column("dnd_weekend_end", sa.String(length=8), server_default="10:00", nullable=False),
    )
    op.add_column(
        "user_settings",
        sa.Column("last_digest_sent_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.execute(
        """
        UPDATE user_settings SET digest_mode = CASE
            WHEN update_interval_minutes <= 0 THEN 'off'
            WHEN update_interval_minutes <= 60 THEN '1h'
            WHEN update_interval_minutes <= 180 THEN '3h'
            WHEN update_interval_minutes <= 360 THEN '6h'
            ELSE 'daily'
        END
        """
    )

    op.add_column("ai_usage_logs", sa.Column("tokens_in", sa.Integer(), nullable=True))
    op.add_column("ai_usage_logs", sa.Column("tokens_out", sa.Integer(), nullable=True))
    op.add_column("ai_usage_logs", sa.Column("user_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        op.f("fk_ai_usage_logs_user_id_users"),
        "ai_usage_logs",
        "users",
        ["user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(op.f("ix_ai_usage_logs_user_id"), "ai_usage_logs", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_ai_usage_logs_user_id"), table_name="ai_usage_logs")
    op.drop_constraint(op.f("fk_ai_usage_logs_user_id_users"), "ai_usage_logs", type_="foreignkey")
    op.drop_column("ai_usage_logs", "user_id")
    op.drop_column("ai_usage_logs", "tokens_out")
    op.drop_column("ai_usage_logs", "tokens_in")

    op.drop_column("user_settings", "last_digest_sent_at")
    op.drop_column("user_settings", "dnd_weekend_end")
    op.drop_column("user_settings", "dnd_weekend_start")
    op.drop_column("user_settings", "dnd_weekday_end")
    op.drop_column("user_settings", "dnd_weekday_start")
    op.drop_column("user_settings", "dnd_enabled")
    op.drop_column("user_settings", "digest_time")
    op.drop_column("user_settings", "digest_mode")
    op.drop_column("user_settings", "theme_weights")
    op.drop_column("user_settings", "timezone")

    op.drop_index(op.f("ix_admin_accounts_role"), table_name="admin_accounts")
    op.drop_index(op.f("ix_admin_accounts_user_id"), table_name="admin_accounts")
    op.drop_table("admin_accounts")

    op.drop_column("users", "banned_at")
    op.drop_column("users", "is_banned")
