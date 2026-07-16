"""Merge policy: attach posts to existing Events or create new ones."""

from __future__ import annotations

import re

from app.services.clustering import CosineClusterer, cosine_similarity
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
    # Same brand + promo wave (e.g. Rostic's + minions + combo + July)
    if len(shared) >= 3 and overlap >= 0.22:
        return True
    # Strong token containment (one title is a paraphrase of the other)
    if shared and min(len(left), len(right)) >= 3:
        smaller = left if len(left) <= len(right) else right
        if len(shared) / len(smaller) >= 0.72:
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
    Find similar Events by embedding + lexical overlap + entity gate.
    Cost: no LLM — only local cosine / token Jaccard.
    """

    def __init__(
        self,
        embedding: EmbeddingPort,
        *,
        threshold: float = 0.85,
        clusterer: CosineClusterer | None = None,
    ) -> None:
        self._embedding = embedding
        # Hashing embeddings are noisier than transformers — auto-relax threshold.
        backend = getattr(embedding, "backend", None) or embedding.__class__.__name__.lower()
        if "hash" in str(backend).lower() and threshold > 0.55:
            threshold = min(threshold, 0.45)
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
        if not result.is_new and result.news_id is not None:
            if self._entity_ok(result.news_id, candidates, entities):
                return result
            soft = self._soft_lexical_match(text, embedding, candidates, entities=entities)
            if soft is not None:
                return soft
            return ClusterResult(news_id=None, similarity=result.similarity, is_new=True)

        soft = self._soft_lexical_match(text, embedding, candidates, entities=entities)
        if soft is not None:
            return soft
        return result

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

    def _soft_lexical_match(
        self,
        text: str,
        embedding: list[float],
        candidates: list[ClusterCandidate],
        *,
        entities: list[str] | None = None,
    ) -> ClusterResult | None:
        """Catch near-duplicates the embedder misses (same promo, different wording)."""
        best_id: int | None = None
        best_score = 0.0
        for cand in candidates:
            blob = f"{cand.title}\n{cand.summary}"
            overlap = content_overlap(text, blob)
            if overlap < 0.24 and not is_near_duplicate(text, blob):
                continue
            try:
                sim = float(cosine_similarity(embedding, list(cand.embedding))) if cand.embedding else 0.0
            except Exception:
                sim = 0.0
            ent_ok = True
            if entities:
                cand_ents = list(cand.entities or []) or [cand.title, cand.summary]
                ent_ok = entities_overlap(entities, cand_ents)
            score = overlap * 0.65 + sim * 0.35
            near = is_near_duplicate(text, blob)
            # Strong near-dupe bypasses entity gate (paraphrases of same story)
            if near or overlap >= 0.42 or (overlap >= 0.28 and sim >= 0.50 and ent_ok) or (
                overlap >= 0.32 and ent_ok and sim >= 0.40
            ) or (sim >= 0.85 and (near or overlap >= 0.20)):
                if score > best_score or (near and best_id is None):
                    best_score = max(score, 0.55 if near else score)
                    best_id = cand.news_id
        if best_id is None:
            return None
        return ClusterResult(news_id=best_id, similarity=best_score, is_new=False)
