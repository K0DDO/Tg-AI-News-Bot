"""Merge policy: attach posts to existing Events or create new ones."""

from __future__ import annotations

import re
from datetime import datetime, timezone

from app.services.clustering import CosineClusterer, cosine_similarity
from app.services.events.similarity import should_merge, similarity_score
from app.services.ports import ClusterCandidate, ClusterResult, EmbeddingPort

_NORM = re.compile(r"[^\w]+", re.UNICODE)
_QUOTED = re.compile(r"[«\"“]([^»\"”]{2,80})[»\"”]")
_PROPER = re.compile(
    r"\b([A-ZА-ЯЁ][\w\-]*(?:\s+[A-ZА-ЯЁ][\w\-]*){0,3})\b",
)
_STOP = {
    "что", "как", "это", "для", "или", "the", "and", "for", "with", "будет",
    "были", "новый", "новые", "новости", "добавят", "появятся", "рамках",
    "всех", "кто", "купит", "вместо", "передают", "источники", "эксклюзив",
}


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


def _stem(token: str) -> str:
    t = token.lower()
    for suf in (
        "ами", "ями", "ов", "ей", "ах", "ях", "ом", "ем",
        "ый", "ая", "ое", "ые", "ии", "ий", "ую", "ой",
    ):
        if len(t) > 5 and t.endswith(suf):
            return t[: -len(suf)]
    if len(t) > 4 and t[-1] in "аеиоуыяю":
        return t[:-1]
    return t


def content_tokens(text: str) -> set[str]:
    toks = {t.lower() for t in re.findall(r"[\w\-]{3,}", text or "", flags=re.UNICODE)}
    return {_stem(t) for t in toks if t not in _STOP and not t.isdigit()}


def content_overlap(a: str, b: str) -> float:
    """Jaccard overlap of significant content tokens (0..1)."""
    left = content_tokens(a)
    right = content_tokens(b)
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def is_near_duplicate(a: str, b: str, *, threshold: float = 0.30) -> bool:
    """True when two stories are essentially the same promo/event."""
    left = content_tokens(a)
    right = content_tokens(b)
    if not left or not right:
        return False
    shared = left & right
    overlap = len(shared) / len(left | right)
    if overlap >= threshold:
        return True
    if len(shared) >= 3 and overlap >= 0.22:
        return True
    if shared and min(len(left), len(right)) >= 3:
        smaller = left if len(left) <= len(right) else right
        if len(shared) / len(smaller) >= 0.72:
            return True
    # Distinctive multi-brand overlap (MAX + Google, Apple + MacBook, …)
    if len(shared) >= 2:
        blob = f"{a} {b}".lower()
        removal = any(
            x in blob
            for x in (
                "удал", "убрал", "исчез", "unavailable", "removed", "banned",
                "delete", "запрет", "недоступ",
            )
        )
        store = any(x in blob for x in ("google", "play", "store", "магазин", "app store"))
        if removal and store and ("max" in shared or "макс" in shared):
            return True
        if len(shared) >= 2 and removal and overlap >= 0.12:
            return True
    return False


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
    Find similar Events via composite similarity_score:
    embedding 60% + entities 20% + keywords 10% + time 10%.
    """

    def __init__(
        self,
        embedding: EmbeddingPort,
        *,
        threshold: float = 0.72,
        clusterer: CosineClusterer | None = None,
        time_window_hours: float = 72.0,
    ) -> None:
        self._embedding = embedding
        backend = getattr(embedding, "backend", None) or embedding.__class__.__name__.lower()
        # Hashing embeddings are noisier — slightly lower merge bar.
        if "hash" in str(backend).lower() and threshold > 0.52:
            threshold = min(threshold, 0.52)
        self._threshold = float(threshold)
        self._time_window_hours = float(time_window_hours)
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
        keywords: list[str] | None = None,
        category: str | None = None,
        created_at: datetime | None = None,
    ) -> ClusterResult:
        """Pick best semantic match by composite score (not cosine alone)."""
        now = created_at or datetime.now(timezone.utc)
        best_id: int | None = None
        best_score = 0.0

        for cand in candidates:
            blob = f"{cand.title}\n{cand.summary}"
            # Cheap prefilter — skip clearly unrelated
            if (
                content_overlap(text, blob) < 0.12
                and not is_near_duplicate(text, blob)
                and not entities_overlap(entities, list(cand.entities or []) or None)
            ):
                # Still allow pure embedding hits
                try:
                    raw_sim = (
                        float(cosine_similarity(embedding, list(cand.embedding)))
                        if cand.embedding
                        else 0.0
                    )
                except Exception:
                    raw_sim = 0.0
                if raw_sim < 0.55:
                    continue

            cand_time = cand.created_at if isinstance(cand.created_at, datetime) else None
            breakdown = similarity_score(
                embedding_a=embedding,
                embedding_b=list(cand.embedding) if cand.embedding else None,
                entities_a=entities,
                entities_b=list(cand.entities or []) or None,
                keywords_a=keywords,
                keywords_b=list(cand.keywords or []) or None,
                text_a=text,
                text_b=blob,
                time_a=now,
                time_b=cand_time,
                category_a=category,
                category_b=cand.category,
                time_window_hours=self._time_window_hours,
            )
            near = is_near_duplicate(text, blob)
            score = breakdown.total
            if near:
                score = max(score, self._threshold)
            if score > best_score:
                best_score = score
                best_id = cand.news_id

        if best_id is not None and should_merge(best_score, threshold=self._threshold):
            return ClusterResult(news_id=best_id, similarity=best_score, is_new=False)

        # Legacy cosine path as last resort for high embed similarity
        result = self._clusterer.assign(text, embedding, candidates, max(self._threshold, 0.85))
        if not result.is_new and result.news_id is not None and result.similarity >= 0.90:
            if self._entity_ok(result.news_id, candidates, entities):
                return result

        return ClusterResult(news_id=None, similarity=best_score, is_new=True)

    def _entity_ok(
        self,
        news_id: int,
        candidates: list[ClusterCandidate],
        entities: list[str] | None,
    ) -> bool:
        if not entities:
            return True
        matched = next((c for c in candidates if c.news_id == news_id), None)
        if matched is None:
            return True
        cand_entities = list(matched.entities or [])
        if not cand_entities:
            cand_entities = [matched.title, matched.summary]
        return entities_overlap(entities, cand_entities)
