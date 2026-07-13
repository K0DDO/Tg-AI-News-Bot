"""Merge policy: attach posts to existing Events or create new ones."""

from __future__ import annotations

import re

from app.services.clustering import CosineClusterer
from app.services.ports import ClusterCandidate, ClusterResult, EmbeddingPort

_NORM = re.compile(r"[^\w]+", re.UNICODE)
_QUOTED = re.compile(r"[«\"“]([^»\"”]{2,80})[»\"”]")
_PROPER = re.compile(
    r"\b([A-ZА-ЯЁ][\w\-]*(?:\s+[A-ZА-ЯЁ][\w\-]*){0,3})\b",
)


def _norm_entity(value: str) -> str:
    return _NORM.sub(" ", (value or "").lower()).strip()


def _entity_tokens(values: list[str] | None) -> set[str]:
    out: set[str] = set()
    for raw in values or []:
        n = _norm_entity(str(raw))
        if not n:
            continue
        out.add(n)
        for part in n.split():
            if len(part) >= 3:
                out.add(part)
    return out


def entities_overlap(a: list[str] | None, b: list[str] | None) -> bool:
    """True if entity sets share a meaningful token, or either side is empty."""
    left = _entity_tokens(a)
    right = _entity_tokens(b)
    if not left or not right:
        return True
    return bool(left & right)


def light_entities_from_text(text: str, *, limit: int = 12) -> list[str]:
    """Cheap entity hints for pre-AI merge (quoted titles + proper nouns)."""
    out: list[str] = []
    seen: set[str] = set()
    for m in _QUOTED.finditer(text or ""):
        val = m.group(1).strip()
        key = _norm_entity(val)
        if key and key not in seen:
            seen.add(key)
            out.append(val)
    for m in _PROPER.finditer(text or ""):
        val = m.group(1).strip()
        if len(val) < 3:
            continue
        key = _norm_entity(val)
        if key and key not in seen:
            seen.add(key)
            out.append(val)
        if len(out) >= limit:
            break
    return out[:limit]


class EventMergeService:
    """
    Find similar Events by embedding + entity overlap gate.
    Cost: no LLM — only local cosine.
    """

    def __init__(
        self,
        embedding: EmbeddingPort,
        *,
        threshold: float = 0.75,
        clusterer: CosineClusterer | None = None,
    ) -> None:
        self._embedding = embedding
        self._threshold = threshold
        self._clusterer = clusterer or CosineClusterer()

    def embed_event_text(
        self,
        *,
        title: str,
        summary: str,
        topic: str | None,
        entities: list[str] | None,
    ) -> list[float]:
        parts = [title, summary, topic or "", " ".join(entities or [])]
        return list(self._embedding.embed_one("\n".join(p for p in parts if p)))

    def find_match(
        self,
        text: str,
        embedding: list[float],
        candidates: list[ClusterCandidate],
        *,
        entities: list[str] | None = None,
    ) -> ClusterResult:
        result = self._clusterer.assign(text, embedding, candidates, self._threshold)
        if result.is_new or result.news_id is None:
            return result
        if not entities:
            return result
        matched = next((c for c in candidates if c.news_id == result.news_id), None)
        if matched is None:
            return result
        cand_entities = list(matched.entities or [])
        if not cand_entities:
            # Fall back to title/summary tokens when candidate has no stored entities
            cand_entities = [matched.title, matched.summary]
        if not entities_overlap(entities, cand_entities):
            return ClusterResult(news_id=None, similarity=result.similarity, is_new=True)
        return result
