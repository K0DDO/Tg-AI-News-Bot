"""Event-centric schema: TelegramPost fields, news→events, timeline, entities.

Revision ID: 006_events
Revises: 005_backfill_sources
Create Date: 2026-07-12
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "006_events"
down_revision: Union[str, None] = "005_backfill_sources"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- TelegramPost enrichment on messages ---
    op.add_column("messages", sa.Column("language", sa.String(length=16), nullable=True))
    op.add_column(
        "messages",
        sa.Column("is_news", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column(
        "messages",
        sa.Column("is_advertisement", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column("messages", sa.Column("raw_embedding", sa.JSON(), nullable=True))
    op.add_column("messages", sa.Column("media", sa.JSON(), nullable=True))
    op.add_column("messages", sa.Column("raw_entities", sa.JSON(), nullable=True))
    op.add_column("messages", sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True))

    # --- Expand topic + new Event fields before rename ---
    op.alter_column(
        "news",
        "topic",
        existing_type=sa.String(length=128),
        type_=sa.String(length=512),
        existing_nullable=True,
    )
    op.add_column("news", sa.Column("entities", sa.JSON(), nullable=True))
    op.add_column("news", sa.Column("keywords", sa.JSON(), nullable=True))
    op.add_column(
        "news",
        sa.Column("status", sa.String(length=32), server_default="active", nullable=False),
    )
    op.add_column("news", sa.Column("timeline", sa.JSON(), nullable=True))
    op.add_column(
        "news",
        sa.Column("posts_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column("news", sa.Column("ai_reasoning", sa.Text(), nullable=True))
    op.add_column("news", sa.Column("related_event_ids", sa.JSON(), nullable=True))
    op.execute("UPDATE news SET posts_count = COALESCE(sources_count, 0)")
    op.execute(
        """
        UPDATE news SET timeline = jsonb_build_array(
            jsonb_build_object(
                'at', to_char(coalesce(created_at, now()) AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'),
                'kind', 'created',
                'text', 'Событие создано',
                'sources', coalesce(sources_count, 0)
            )
        )
        WHERE timeline IS NULL
        """
    )
    op.create_index("ix_news_status", "news", ["status"], unique=False)

    # Drop FKs that point at news before rename
    op.drop_constraint(op.f("fk_news_sources_news_id_news"), "news_sources", type_="foreignkey")
    op.drop_constraint(op.f("fk_reactions_news_id_news"), "reactions", type_="foreignkey")
    op.drop_constraint("fk_user_news_states_news_id_news", "user_news_states", type_="foreignkey")
    op.drop_constraint("uq_user_news_states_user_id_news_id", "user_news_states", type_="unique")
    op.drop_constraint("uq_reactions_user_id_news_id", "reactions", type_="unique")

    op.rename_table("news", "events")
    op.execute("ALTER INDEX IF EXISTS ix_news_topic RENAME TO ix_events_topic")
    op.execute("ALTER INDEX IF EXISTS ix_news_category RENAME TO ix_events_category")
    op.execute("ALTER INDEX IF EXISTS ix_news_importance_score RENAME TO ix_events_importance_score")
    op.execute("ALTER INDEX IF EXISTS ix_news_created_at RENAME TO ix_events_created_at")
    op.execute("ALTER INDEX IF EXISTS ix_news_status RENAME TO ix_events_status")
    op.execute("ALTER INDEX IF EXISTS pk_news RENAME TO pk_events")

    # news_sources → event_sources
    op.alter_column("news_sources", "news_id", new_column_name="event_id")
    op.rename_table("news_sources", "event_sources")
    op.execute("ALTER INDEX IF EXISTS ix_news_sources_news_id RENAME TO ix_event_sources_event_id")
    op.execute("ALTER INDEX IF EXISTS ix_news_sources_message_id RENAME TO ix_event_sources_message_id")
    op.execute("ALTER INDEX IF EXISTS pk_news_sources RENAME TO pk_event_sources")
    op.create_foreign_key(
        op.f("fk_event_sources_event_id_events"),
        "event_sources",
        "events",
        ["event_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # user_news_states → user_event_states
    op.alter_column("user_news_states", "news_id", new_column_name="event_id")
    op.rename_table("user_news_states", "user_event_states")
    op.execute("ALTER INDEX IF EXISTS ix_user_news_states_user_id RENAME TO ix_user_event_states_user_id")
    op.execute("ALTER INDEX IF EXISTS ix_user_news_states_news_id RENAME TO ix_user_event_states_event_id")
    op.execute("ALTER INDEX IF EXISTS pk_user_news_states RENAME TO pk_user_event_states")
    op.create_foreign_key(
        op.f("fk_user_event_states_event_id_events"),
        "user_event_states",
        "events",
        ["event_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_unique_constraint(
        "uq_user_event_states_user_id_event_id",
        "user_event_states",
        ["user_id", "event_id"],
    )

    # reactions
    op.alter_column("reactions", "news_id", new_column_name="event_id")
    op.execute("ALTER INDEX IF EXISTS ix_reactions_news_id RENAME TO ix_reactions_event_id")
    op.create_foreign_key(
        op.f("fk_reactions_event_id_events"),
        "reactions",
        "events",
        ["event_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_unique_constraint(
        "uq_reactions_user_id_event_id",
        "reactions",
        ["user_id", "event_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_reactions_user_id_event_id", "reactions", type_="unique")
    op.drop_constraint(op.f("fk_reactions_event_id_events"), "reactions", type_="foreignkey")
    op.alter_column("reactions", "event_id", new_column_name="news_id")

    op.drop_constraint("uq_user_event_states_user_id_event_id", "user_event_states", type_="unique")
    op.drop_constraint(op.f("fk_user_event_states_event_id_events"), "user_event_states", type_="foreignkey")
    op.rename_table("user_event_states", "user_news_states")
    op.alter_column("user_news_states", "event_id", new_column_name="news_id")

    op.drop_constraint(op.f("fk_event_sources_event_id_events"), "event_sources", type_="foreignkey")
    op.rename_table("event_sources", "news_sources")
    op.alter_column("news_sources", "event_id", new_column_name="news_id")

    op.rename_table("events", "news")

    op.create_foreign_key(
        op.f("fk_news_sources_news_id_news"),
        "news_sources",
        "news",
        ["news_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_user_news_states_news_id_news",
        "user_news_states",
        "news",
        ["news_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_unique_constraint(
        "uq_user_news_states_user_id_news_id",
        "user_news_states",
        ["user_id", "news_id"],
    )
    op.create_foreign_key(
        op.f("fk_reactions_news_id_news"),
        "reactions",
        "news",
        ["news_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_unique_constraint("uq_reactions_user_id_news_id", "reactions", ["user_id", "news_id"])

    op.drop_index("ix_events_status", table_name="news")
    op.drop_column("news", "related_event_ids")
    op.drop_column("news", "ai_reasoning")
    op.drop_column("news", "posts_count")
    op.drop_column("news", "timeline")
    op.drop_column("news", "status")
    op.drop_column("news", "keywords")
    op.drop_column("news", "entities")
    op.alter_column(
        "news",
        "topic",
        existing_type=sa.String(length=512),
        type_=sa.String(length=128),
        existing_nullable=True,
    )

    op.drop_column("messages", "processed_at")
    op.drop_column("messages", "raw_entities")
    op.drop_column("messages", "media")
    op.drop_column("messages", "raw_embedding")
    op.drop_column("messages", "is_advertisement")
    op.drop_column("messages", "is_news")
    op.drop_column("messages", "language")
