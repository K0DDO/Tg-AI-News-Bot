"""Knowledge Graph service — incremental upsert of Nodes/Edges from Events."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Edge, Event, EventNode, Node
from app.services.knowledge.aliases import ALIAS_MAP, SEED_EDGES, slugify

logger = logging.getLogger(__name__)

_TOKEN = re.compile(r"[\w\-]{2,}", re.UNICODE)
_STRONG_WEIGHT = Decimal("0.30")
_MAX_WEIGHT = Decimal("1.0")
_MIN_WEIGHT = Decimal("0.05")


@dataclass(frozen=True, slots=True)
class ResolvedEntity:
    name: str
    node_type: str
    categories: tuple[str, ...]
    raw: str


@dataclass(slots=True)
class RankedEvent:
    event: Event
    score: float
    semantic: float
    graph_distance: float
    sources: float
    importance: float
    freshness: float
    personal: float
    matched_nodes: list[str]
    explanation: list[str]


class KnowledgeGraphService:
    """Incremental KG builder + query helpers. Never duplicates Nodes by slug."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._seeded = False

    async def ensure_seed(self) -> None:
        if self._seeded:
            return
        for alias, (name, ntype, cats) in ALIAS_MAP.items():
            node = await self.upsert_node(name, ntype, aliases=[alias], categories=list(cats))
            _ = node
        for a, b, etype in SEED_EDGES:
            na = await self.get_node_by_name(a)
            nb = await self.get_node_by_name(b)
            if na and nb:
                await self.upsert_edge(na.id, nb.id, etype, bump=False, weight=Decimal("0.85"), confidence=Decimal("0.95"))
        await self._session.flush()
        self._seeded = True

    async def ingest_event(self, event: Event, *, extra_entities: list[str] | None = None) -> list[Node]:
        """Extract/link entities from Event → Nodes/Edges/EventNode. Idempotent."""
        await self.ensure_seed()
        names = list(event.entities or []) + list(event.keywords or [])
        if extra_entities:
            names.extend(extra_entities)
        # Also pull known aliases from title/summary
        blob = f"{event.title} {event.summary} {event.topic or ''}"
        names.extend(self._scan_known_aliases(blob))
        resolved = self.resolve_entities(names)
        if not resolved and event.category:
            resolved = self.resolve_entities([event.category])

        nodes: list[Node] = []
        for ent in resolved:
            node = await self.upsert_node(
                ent.name,
                ent.node_type,
                aliases=[ent.raw],
                categories=list(ent.categories),
            )
            node.mention_count = int(node.mention_count or 0) + 1
            await self.link_event_node(event.id, node.id)
            nodes.append(node)

        # Co-occurrence edges between entities in the same event
        for i, a in enumerate(nodes):
            for b in nodes[i + 1 :]:
                await self.upsert_edge(a.id, b.id, "RELATED_TO", bump=True)
                await self.upsert_edge(b.id, a.id, "RELATED_TO", bump=True)

        # Link products to parent companies via seed / categories
        for node in nodes:
            for cat in node.semantic_categories or []:
                parent = await self.get_node_by_name(cat)
                if parent and parent.id != node.id:
                    await self.upsert_edge(parent.id, node.id, "RELATED_TO", bump=True)
                    await self.upsert_edge(node.id, parent.id, "PART_OF", bump=True)

        # related events via shared nodes
        if nodes:
            await self._update_related_events(event, [n.id for n in nodes])

        await self._session.flush()
        return nodes

    async def _drop_self_edge(self, node_id: int) -> None:
        result = await self._session.execute(
            select(Edge).where(
                Edge.from_node_id == node_id,
                Edge.to_node_id == node_id,
            )
        )
        for edge in result.scalars().all():
            await self._session.delete(edge)

    def resolve_entities(self, names: list[str]) -> list[ResolvedEntity]:
        out: list[ResolvedEntity] = []
        seen: set[str] = set()
        for raw in names:
            r = self.resolve_one(str(raw))
            if not r:
                continue
            key = r.name.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(r)
        return out

    def resolve_one(self, raw: str) -> ResolvedEntity | None:
        text = (raw or "").strip()
        if len(text) < 2:
            return None
        key = text.lower()
        # direct + spaced variants
        for candidate in (key, key.replace("-", " "), re.sub(r"\s+", " ", key)):
            if candidate in ALIAS_MAP:
                name, ntype, cats = ALIAS_MAP[candidate]
                return ResolvedEntity(name=name, node_type=ntype, categories=cats, raw=text)
        # substring alias match for compounds like "iPhone 18 Pro Max"
        best: tuple[str, str, tuple[str, ...]] | None = None
        best_len = 0
        for alias, triple in ALIAS_MAP.items():
            if len(alias) >= 3 and alias in key and len(alias) > best_len:
                best = triple
                best_len = len(alias)
        if best:
            name, ntype, cats = best
            return ResolvedEntity(name=name, node_type=ntype, categories=cats, raw=text)
        # Unknown proper-ish token → Topic/Product heuristic
        if not re.search(r"[A-Za-zА-Яа-я]", text):
            return None
        ntype = "Product" if re.search(r"\d", text) else "Topic"
        if text[:1].isupper() or any(c.isupper() for c in text[1:]):
            if ntype == "Topic":
                ntype = "Company" if len(text.split()) == 1 and len(text) <= 16 else "Product"
        return ResolvedEntity(name=text[:256], node_type=ntype, categories=(), raw=text)

    def _scan_known_aliases(self, text: str) -> list[str]:
        low = (text or "").lower()
        hits: list[str] = []
        for alias in sorted(ALIAS_MAP.keys(), key=len, reverse=True):
            if len(alias) >= 3 and alias in low:
                hits.append(ALIAS_MAP[alias][0])
        return hits[:12]

    async def upsert_node(
        self,
        name: str,
        node_type: str,
        *,
        aliases: list[str] | None = None,
        categories: list[str] | None = None,
    ) -> Node:
        slug = slugify(name)
        result = await self._session.execute(select(Node).where(Node.slug == slug))
        node = result.scalar_one_or_none()
        if node is None:
            # try alias match
            if aliases:
                for a in aliases:
                    found = await self.find_node_by_alias(a)
                    if found:
                        node = found
                        break
        if node is None:
            node = Node(
                name=name[:256],
                slug=slug,
                node_type=node_type if node_type in {
                    "Company", "Person", "Product", "Technology", "Organization", "Country", "Topic"
                } else "Topic",
                aliases=list({*(aliases or []), name.lower()})[:32],
                semantic_categories=list(categories or [])[:16],
                mention_count=0,
            )
            self._session.add(node)
            await self._session.flush()
            return node

        # merge aliases / categories
        als = list(node.aliases or [])
        for a in aliases or []:
            al = a.lower().strip()
            if al and al not in als:
                als.append(al)
        node.aliases = als[:48]
        cats = list(node.semantic_categories or [])
        for c in categories or []:
            if c and c not in cats:
                cats.append(c)
        node.semantic_categories = cats[:24]
        node.updated_at = datetime.now(timezone.utc)
        return node

    async def find_node_by_alias(self, alias: str) -> Node | None:
        key = (alias or "").strip().lower()
        if not key:
            return None
        if key in ALIAS_MAP:
            return await self.get_node_by_name(ALIAS_MAP[key][0])
        result = await self._session.execute(select(Node).where(Node.slug == slugify(key)))
        node = result.scalar_one_or_none()
        if node:
            return node
        # JSON contains is DB-specific; fallback scan recent nodes is expensive — use name ilike
        result = await self._session.execute(
            select(Node).where(or_(Node.name.ilike(key), Node.slug == slugify(key))).limit(1)
        )
        return result.scalar_one_or_none()

    async def get_node_by_name(self, name: str) -> Node | None:
        result = await self._session.execute(select(Node).where(Node.slug == slugify(name)))
        return result.scalar_one_or_none()

    async def upsert_edge(
        self,
        from_id: int,
        to_id: int,
        edge_type: str,
        *,
        bump: bool = True,
        weight: Decimal | None = None,
        confidence: Decimal | None = None,
    ) -> Edge | None:
        if from_id == to_id:
            return None
        result = await self._session.execute(
            select(Edge).where(
                Edge.from_node_id == from_id,
                Edge.to_node_id == to_id,
                Edge.edge_type == edge_type,
            )
        )
        edge = result.scalar_one_or_none()
        now = datetime.now(timezone.utc)
        if edge is None:
            edge = Edge(
                from_node_id=from_id,
                to_node_id=to_id,
                edge_type=edge_type,
                weight=weight or Decimal("0.45"),
                confidence=confidence or Decimal("0.55"),
                mentions=1,
                first_seen=now,
                last_seen=now,
            )
            self._session.add(edge)
            await self._session.flush()
            return edge
        if bump:
            edge.mentions = int(edge.mentions or 0) + 1
            # self-learning: strengthen on reconfirmation
            edge.weight = min(_MAX_WEIGHT, Decimal(str(edge.weight)) + Decimal("0.04"))
            edge.confidence = min(_MAX_WEIGHT, Decimal(str(edge.confidence)) + Decimal("0.03"))
            edge.last_seen = now
            edge.updated_at = now
        elif weight is not None:
            edge.weight = max(Decimal(str(edge.weight)), weight)
            if confidence is not None:
                edge.confidence = max(Decimal(str(edge.confidence)), confidence)
        return edge

    async def link_event_node(
        self,
        event_id: int,
        node_id: int,
        *,
        relation: str = "CONNECTED_TO",
        confidence: float = 0.75,
    ) -> EventNode:
        result = await self._session.execute(
            select(EventNode).where(
                EventNode.event_id == event_id,
                EventNode.node_id == node_id,
            )
        )
        link = result.scalar_one_or_none()
        if link:
            link.confidence = max(float(link.confidence or 0), confidence)
            return link
        link = EventNode(
            event_id=event_id,
            node_id=node_id,
            relation=relation,
            confidence=confidence,
        )
        self._session.add(link)
        await self._session.flush()
        return link

    async def expand_nodes(
        self,
        node_ids: list[int],
        *,
        min_weight: Decimal = _STRONG_WEIGHT,
        max_extra: int = 12,
    ) -> list[tuple[Node, int]]:
        """Graph expansion: seed nodes + strong neighbors. Returns (node, distance)."""
        if not node_ids:
            return []
        result = await self._session.execute(select(Node).where(Node.id.in_(node_ids)))
        seeds = list(result.scalars().all())
        out: dict[int, tuple[Node, int]] = {n.id: (n, 0) for n in seeds}

        result = await self._session.execute(
            select(Edge).where(
                or_(Edge.from_node_id.in_(node_ids), Edge.to_node_id.in_(node_ids)),
                Edge.weight >= min_weight,
            )
        )
        neighbor_ids: set[int] = set()
        for edge in result.scalars().all():
            if edge.from_node_id in out:
                neighbor_ids.add(edge.to_node_id)
            if edge.to_node_id in out:
                neighbor_ids.add(edge.from_node_id)
        neighbor_ids -= set(out)
        if neighbor_ids:
            result = await self._session.execute(
                select(Node).where(Node.id.in_(list(neighbor_ids)[:max_extra]))
            )
            for n in result.scalars().all():
                out[n.id] = (n, 1)
        return sorted(out.values(), key=lambda x: (x[1], -x[0].mention_count))

    async def event_ids_for_nodes(self, node_ids: list[int], *, limit: int = 400) -> set[int]:
        if not node_ids:
            return set()
        result = await self._session.execute(
            select(EventNode.event_id)
            .where(EventNode.node_id.in_(node_ids))
            .limit(limit)
        )
        return set(result.scalars().all())

    async def nodes_for_event(self, event_id: int) -> list[Node]:
        result = await self._session.execute(
            select(Node)
            .join(EventNode, EventNode.node_id == Node.id)
            .where(EventNode.event_id == event_id)
        )
        return list(result.scalars().all())

    async def related_events(self, event: Event, *, limit: int = 6) -> list[Event]:
        nodes = await self.nodes_for_event(event.id)
        if not nodes:
            return []
        ids = await self.event_ids_for_nodes([n.id for n in nodes], limit=200)
        ids.discard(event.id)
        if not ids:
            return []
        result = await self._session.execute(
            select(Event)
            .where(Event.id.in_(list(ids)))
            .where(Event.status == "active")
            .order_by(Event.importance_score.desc(), Event.updated_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def _update_related_events(self, event: Event, node_ids: list[int]) -> None:
        related = await self.event_ids_for_nodes(node_ids, limit=80)
        related.discard(event.id)
        # keep top by shared — store ids on Event.related_event_ids
        top = list(related)[:12]
        event.related_event_ids = top
        # bidirectional light update for a few peers
        for rid in top[:5]:
            peer = await self._session.get(Event, rid)
            if not peer:
                continue
            peers = list(peer.related_event_ids or [])
            if event.id not in peers:
                peers = [event.id, *peers][:12]
                peer.related_event_ids = peers

    async def decay_stale_edges(self, *, older_than_days: int = 45, factor: float = 0.92) -> int:
        """Gradually weaken edges not seen recently (self-learning decay)."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)
        result = await self._session.execute(
            select(Edge).where(Edge.last_seen < cutoff).limit(500)
        )
        n = 0
        for edge in result.scalars().all():
            w = Decimal(str(edge.weight)) * Decimal(str(factor))
            edge.weight = max(_MIN_WEIGHT, w)
            edge.updated_at = datetime.now(timezone.utc)
            n += 1
        await self._session.flush()
        return n

    async def resolve_query_nodes(self, query: str, *, read_only: bool = False) -> list[Node]:
        """Map query tokens to KG nodes. read_only=True never creates new nodes."""
        await self.ensure_seed()
        names = self._scan_known_aliases(query)
        for tok in _TOKEN.findall(query or ""):
            if len(tok) >= 3:
                names.append(tok)
        resolved = self.resolve_entities(names)
        nodes: list[Node] = []
        seen: set[int] = set()
        for ent in resolved:
            if read_only:
                # Only attach to existing nodes (alias / slug lookup)
                found = await self.find_node_by_alias(ent.name)
                if found is None:
                    found = await self.find_node_by_alias(ent.raw)
                if found is None:
                    slug = slugify(ent.name)
                    found = (
                        await self._session.execute(select(Node).where(Node.slug == slug))
                    ).scalar_one_or_none()
                if found is None:
                    continue
                node = found
            else:
                node = await self.upsert_node(
                    ent.name,
                    ent.node_type,
                    aliases=[ent.raw],
                    categories=list(ent.categories),
                )
            if node.id not in seen:
                seen.add(node.id)
                nodes.append(node)
        return nodes

    async def backfill_events(self, *, limit: int = 300) -> int:
        """One-shot: ingest recent events missing graph links."""
        result = await self._session.execute(
            select(Event)
            .where(Event.status == "active")
            .order_by(Event.updated_at.desc())
            .limit(limit)
        )
        n = 0
        for event in result.scalars().all():
            existing = await self._session.execute(
                select(EventNode.id).where(EventNode.event_id == event.id).limit(1)
            )
            if existing.scalar_one_or_none():
                continue
            await self.ingest_event(event)
            n += 1
        await self._session.flush()
        return n

    async def rebuild_maintenance(self) -> dict[str, int]:
        """Repair KG: decay, drop self-edges, prune orphans, merge dupes, backfill."""
        from sqlalchemy import delete, func

        old_nodes = int(await self._session.scalar(select(func.count()).select_from(Node)) or 0)
        old_edges = int(await self._session.scalar(select(func.count()).select_from(Edge)) or 0)
        decayed = await self.decay_stale_edges()

        self_edges = list(
            (
                await self._session.execute(
                    select(Edge).where(Edge.from_node_id == Edge.to_node_id)
                )
            ).scalars().all()
        )
        fixed = 0
        for edge in self_edges:
            await self._session.delete(edge)
            fixed += 1

        dup_slugs = list(
            (
                await self._session.execute(
                    select(Node.slug, func.count()).group_by(Node.slug).having(func.count() > 1)
                )
            ).all()
        )
        merged = 0
        for slug, _cnt in dup_slugs:
            rows = list(
                (
                    await self._session.execute(
                        select(Node).where(Node.slug == slug).order_by(Node.id.asc())
                    )
                ).scalars().all()
            )
            if len(rows) < 2:
                continue
            keep = rows[0]
            for dup in rows[1:]:
                for edge in (
                    await self._session.execute(
                        select(Edge).where(
                            (Edge.from_node_id == dup.id) | (Edge.to_node_id == dup.id)
                        )
                    )
                ).scalars().all():
                    if edge.from_node_id == dup.id:
                        edge.from_node_id = keep.id
                    if edge.to_node_id == dup.id:
                        edge.to_node_id = keep.id
                    if edge.from_node_id == edge.to_node_id:
                        await self._session.delete(edge)
                for link in (
                    await self._session.execute(
                        select(EventNode).where(EventNode.node_id == dup.id)
                    )
                ).scalars().all():
                    link.node_id = keep.id
                keep.mention_count = int(keep.mention_count or 0) + int(dup.mention_count or 0)
                await self._session.delete(dup)
                merged += 1
                fixed += 1

        orphans = list(
            (
                await self._session.execute(
                    select(Node)
                    .where(
                        Node.node_type == "Topic",
                        Node.mention_count <= 1,
                        ~select(EventNode.id).where(EventNode.node_id == Node.id).exists(),
                    )
                    .limit(500)
                )
            ).scalars().all()
        )
        deleted = 0
        for node in orphans:
            await self._session.execute(
                delete(Edge).where(
                    (Edge.from_node_id == node.id) | (Edge.to_node_id == node.id)
                )
            )
            await self._session.delete(node)
            deleted += 1

        backfilled = await self.backfill_events(limit=400)
        await self._session.commit()
        new_nodes = int(await self._session.scalar(select(func.count()).select_from(Node)) or 0)
        return {
            "old_nodes": old_nodes,
            "new_nodes": new_nodes,
            "old_edges": old_edges,
            "decayed": decayed,
            "fixed": fixed,
            "merged_duplicates": merged,
            "deleted": deleted,
            "backfilled_events": backfilled,
        }
