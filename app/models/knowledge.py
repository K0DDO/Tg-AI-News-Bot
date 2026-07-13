"""Knowledge Graph: Node, Edge, EventNode — world knowledge over Events."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.database.base import Base

NODE_TYPES = (
    "Company",
    "Person",
    "Product",
    "Technology",
    "Organization",
    "Country",
    "Topic",
)

EDGE_TYPES = (
    "CREATED",
    "OWNS",
    "PRODUCES",
    "USES",
    "RELATED_TO",
    "PART_OF",
    "COMPETES_WITH",
    "MENTIONS",
    "FOUNDED_BY",
    "WORKS_AT",
    "CONNECTED_TO",
    "SUCCESSOR_OF",
    "PREDECESSOR_OF",
    "CUSTOM",
)


class Node(Base):
    """One knowledge object (company, person, product, …)."""

    __tablename__ = "kg_nodes"
    __table_args__ = (UniqueConstraint("slug", name="uq_kg_nodes_slug"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    slug: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    node_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    aliases: Mapped[list | None] = mapped_column(JSON, nullable=True)
    semantic_categories: Mapped[list | None] = mapped_column(JSON, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    mention_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    event_links = relationship("EventNode", back_populates="node", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Node {self.node_type}:{self.name!r}>"


class Edge(Base):
    """Directed weighted link between two Nodes."""

    __tablename__ = "kg_edges"
    __table_args__ = (
        UniqueConstraint(
            "from_node_id",
            "to_node_id",
            "edge_type",
            name="uq_kg_edges_from_to_type",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    from_node_id: Mapped[int] = mapped_column(
        ForeignKey("kg_nodes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    to_node_id: Mapped[int] = mapped_column(
        ForeignKey("kg_nodes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    edge_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    weight: Mapped[Decimal] = mapped_column(
        Numeric(6, 4), default=Decimal("0.5"), server_default="0.5", nullable=False
    )
    confidence: Mapped[Decimal] = mapped_column(
        Numeric(6, 4), default=Decimal("0.5"), server_default="0.5", nullable=False
    )
    mentions: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    first_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    from_node = relationship("Node", foreign_keys=[from_node_id])
    to_node = relationship("Node", foreign_keys=[to_node_id])


class EventNode(Base):
    """Links a shared Event to knowledge Nodes (Event is not duplicated as a Node)."""

    __tablename__ = "event_nodes"
    __table_args__ = (
        UniqueConstraint("event_id", "node_id", name="uq_event_nodes_event_node"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True
    )
    node_id: Mapped[int] = mapped_column(
        ForeignKey("kg_nodes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    relation: Mapped[str] = mapped_column(
        String(32), default="CONNECTED_TO", server_default="CONNECTED_TO", nullable=False
    )
    confidence: Mapped[float] = mapped_column(Float, default=0.7, server_default="0.7", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    node = relationship("Node", back_populates="event_links")
    event = relationship("Event")
