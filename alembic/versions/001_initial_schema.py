"""Initial schema: users, channels, messages, news, reactions.

Revision ID: 001_initial
Revises:
Create Date: 2026-07-11
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("telegram_id", name=op.f("uq_users_telegram_id")),
    )
    op.create_index(op.f("ix_users_telegram_id"), "users", ["telegram_id"], unique=False)

    op.create_table(
        "channels",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(length=255), nullable=True),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_channels")),
        sa.UniqueConstraint("telegram_id", name=op.f("uq_channels_telegram_id")),
    )
    op.create_index(op.f("ix_channels_telegram_id"), "channels", ["telegram_id"], unique=False)
    op.create_index(op.f("ix_channels_username"), "channels", ["username"], unique=False)

    op.create_table(
        "news",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=128), nullable=True),
        sa.Column(
            "importance_score",
            sa.Numeric(precision=4, scale=2),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_news")),
    )
    op.create_index(op.f("ix_news_category"), "news", ["category"], unique=False)
    op.create_index(op.f("ix_news_importance_score"), "news", ["importance_score"], unique=False)
    op.create_index(op.f("ix_news_created_at"), "news", ["created_at"], unique=False)

    op.create_table(
        "user_channels",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("channel_id", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["channel_id"],
            ["channels.id"],
            name=op.f("fk_user_channels_channel_id_channels"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_channels_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_channels")),
        sa.UniqueConstraint("user_id", "channel_id", name="uq_user_channels_user_id_channel_id"),
    )

    op.create_table(
        "messages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("channel_id", sa.Integer(), nullable=False),
        sa.Column("telegram_message_id", sa.BigInteger(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("url", sa.String(length=1024), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="raw", nullable=False),
        sa.Column("filter_reason", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["channel_id"],
            ["channels.id"],
            name=op.f("fk_messages_channel_id_channels"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_messages")),
        sa.UniqueConstraint(
            "channel_id",
            "telegram_message_id",
            name="uq_messages_channel_id_telegram_message_id",
        ),
    )
    op.create_index(op.f("ix_messages_channel_id"), "messages", ["channel_id"], unique=False)
    op.create_index(op.f("ix_messages_published_at"), "messages", ["published_at"], unique=False)
    op.create_index(op.f("ix_messages_status"), "messages", ["status"], unique=False)

    op.create_table(
        "reactions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("news_id", sa.Integer(), nullable=False),
        sa.Column("reaction_type", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["news_id"],
            ["news.id"],
            name=op.f("fk_reactions_news_id_news"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_reactions_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reactions")),
        sa.UniqueConstraint("user_id", "news_id", name="uq_reactions_user_id_news_id"),
    )
    op.create_index(op.f("ix_reactions_user_id"), "reactions", ["user_id"], unique=False)
    op.create_index(op.f("ix_reactions_news_id"), "reactions", ["news_id"], unique=False)

    op.create_table(
        "news_sources",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("news_id", sa.Integer(), nullable=False),
        sa.Column("message_id", sa.Integer(), nullable=True),
        sa.Column("source_url", sa.String(length=1024), nullable=False),
        sa.Column("channel_title", sa.String(length=512), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["messages.id"],
            name=op.f("fk_news_sources_message_id_messages"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["news_id"],
            ["news.id"],
            name=op.f("fk_news_sources_news_id_news"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_news_sources")),
    )
    op.create_index(op.f("ix_news_sources_news_id"), "news_sources", ["news_id"], unique=False)
    op.create_index(op.f("ix_news_sources_message_id"), "news_sources", ["message_id"], unique=False)


def downgrade() -> None:
    op.drop_table("news_sources")
    op.drop_table("reactions")
    op.drop_table("messages")
    op.drop_table("user_channels")
    op.drop_table("news")
    op.drop_table("channels")
    op.drop_table("users")
