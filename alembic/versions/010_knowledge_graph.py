"""Add Knowledge Graph tables: kg_nodes, kg_edges, event_nodes.

Revision ID: 010_knowledge_graph
Revises: 009_backfill_jobs
Create Date: 2026-07-13
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "010_knowledge_graph"
down_revision: Union[str, None] = "009_backfill_jobs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "kg_nodes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("slug", sa.String(length=256), nullable=False),
        sa.Column("node_type", sa.String(length=32), nullable=False),
        sa.Column("aliases", sa.JSON(), nullable=True),
        sa.Column("semantic_categories", sa.JSON(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("mention_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_kg_nodes")),
        sa.UniqueConstraint("slug", name="uq_kg_nodes_slug"),
    )
    op.create_index(op.f("ix_kg_nodes_name"), "kg_nodes", ["name"], unique=False)
    op.create_index(op.f("ix_kg_nodes_slug"), "kg_nodes", ["slug"], unique=False)
    op.create_index(op.f("ix_kg_nodes_node_type"), "kg_nodes", ["node_type"], unique=False)

    op.create_table(
        "kg_edges",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("from_node_id", sa.Integer(), nullable=False),
        sa.Column("to_node_id", sa.Integer(), nullable=False),
        sa.Column("edge_type", sa.String(length=32), nullable=False),
        sa.Column("weight", sa.Numeric(6, 4), server_default="0.5", nullable=False),
        sa.Column("confidence", sa.Numeric(6, 4), server_default="0.5", nullable=False),
        sa.Column("mentions", sa.Integer(), server_default="1", nullable=False),
        sa.Column("first_seen", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_seen", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["from_node_id"],
            ["kg_nodes.id"],
            name=op.f("fk_kg_edges_from_node_id_kg_nodes"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["to_node_id"],
            ["kg_nodes.id"],
            name=op.f("fk_kg_edges_to_node_id_kg_nodes"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_kg_edges")),
        sa.UniqueConstraint("from_node_id", "to_node_id", "edge_type", name="uq_kg_edges_from_to_type"),
    )
    op.create_index(op.f("ix_kg_edges_from_node_id"), "kg_edges", ["from_node_id"], unique=False)
    op.create_index(op.f("ix_kg_edges_to_node_id"), "kg_edges", ["to_node_id"], unique=False)
    op.create_index(op.f("ix_kg_edges_edge_type"), "kg_edges", ["edge_type"], unique=False)

    op.create_table(
        "event_nodes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("node_id", sa.Integer(), nullable=False),
        sa.Column("relation", sa.String(length=32), server_default="CONNECTED_TO", nullable=False),
        sa.Column("confidence", sa.Float(), server_default="0.7", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["events.id"],
            name=op.f("fk_event_nodes_event_id_events"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["node_id"],
            ["kg_nodes.id"],
            name=op.f("fk_event_nodes_node_id_kg_nodes"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_event_nodes")),
        sa.UniqueConstraint("event_id", "node_id", name="uq_event_nodes_event_node"),
    )
    op.create_index(op.f("ix_event_nodes_event_id"), "event_nodes", ["event_id"], unique=False)
    op.create_index(op.f("ix_event_nodes_node_id"), "event_nodes", ["node_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_event_nodes_node_id"), table_name="event_nodes")
    op.drop_index(op.f("ix_event_nodes_event_id"), table_name="event_nodes")
    op.drop_table("event_nodes")
    op.drop_index(op.f("ix_kg_edges_edge_type"), table_name="kg_edges")
    op.drop_index(op.f("ix_kg_edges_to_node_id"), table_name="kg_edges")
    op.drop_index(op.f("ix_kg_edges_from_node_id"), table_name="kg_edges")
    op.drop_table("kg_edges")
    op.drop_index(op.f("ix_kg_nodes_node_type"), table_name="kg_nodes")
    op.drop_index(op.f("ix_kg_nodes_slug"), table_name="kg_nodes")
    op.drop_index(op.f("ix_kg_nodes_name"), table_name="kg_nodes")
    op.drop_table("kg_nodes")
