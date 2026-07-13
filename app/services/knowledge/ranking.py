"""Multi-factor event ranking for Knowledge Graph search."""

from __future__ import annotations

from datetime import datetime, timezone

from app.models import Event
from app.services.clustering import cosine_similarity
from app.services.knowledge.service import RankedEvent


def freshness_score(event: Event, *, now: datetime | None = None) -> float:
    now = now or datetime.now(timezone.utc)
    ts = event.updated_at or event.created_at
    if ts is None:
        return 0.0
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    hours = max(0.0, (now - ts).total_seconds() / 3600.0)
    # 1.0 within 6h, ~0.5 at 3 days, low after 2 weeks
    return max(0.0, min(1.0, 1.0 - (hours / (24 * 14))))


def sources_score(event: Event) -> float:
    n = int(event.sources_count or 0)
    return max(0.0, min(1.0, n / 12.0))


def importance_norm(event: Event) -> float:
    return max(0.0, min(1.0, float(event.importance_score or 0) / 10.0))


def graph_distance_score(distance: int) -> float:
    if distance <= 0:
        return 1.0
    if distance == 1:
        return 0.65
    return 0.35


def combine_scores(
    *,
    semantic: float,
    graph_distance: float,
    sources: float,
    importance: float,
    freshness: float,
    personal: float = 0.0,
) -> float:
    """
    35% semantic · 20% graph · 15% sources · 10% importance · 10% freshness · 10% personal
    """
    return (
        0.35 * semantic
        + 0.20 * graph_distance
        + 0.15 * sources
        + 0.10 * importance
        + 0.10 * freshness
        + 0.10 * personal
    )


def rank_event(
    event: Event,
    *,
    query_embedding: list[float] | None,
    distance: int,
    matched_nodes: list[str],
    personal: float = 0.0,
    via_graph: bool = True,
) -> RankedEvent:
    if query_embedding and event.embedding:
        try:
            semantic = float(cosine_similarity(query_embedding, list(event.embedding)))
        except Exception:
            semantic = 0.0
    else:
        semantic = 0.35 if matched_nodes else 0.15
    semantic = max(0.0, min(1.0, semantic))
    g = graph_distance_score(distance)
    src = sources_score(event)
    imp = importance_norm(event)
    fr = freshness_score(event)
    score = combine_scores(
        semantic=semantic,
        graph_distance=g,
        sources=src,
        importance=imp,
        freshness=fr,
        personal=max(0.0, min(1.0, personal)),
    )
    explanation: list[str] = []
    for name in matched_nodes[:4]:
        explanation.append(f"связано с {name}")
    if via_graph:
        explanation.append("найдено через Knowledge Graph")
    if int(event.sources_count or 0) >= 2:
        explanation.append(f"подтверждено {event.sources_count} источниками")
    if fr >= 0.7:
        explanation.append("опубликовано недавно")
    if imp >= 0.6:
        explanation.append("высокая важность")
    return RankedEvent(
        event=event,
        score=score,
        semantic=semantic,
        graph_distance=g,
        sources=src,
        importance=imp,
        freshness=fr,
        personal=personal,
        matched_nodes=matched_nodes,
        explanation=explanation,
    )


# Secondary relevance: drop weak matches
SECONDARY_THRESHOLD = 0.28
DEEP_SECONDARY_THRESHOLD = 0.22
