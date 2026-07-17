"""Semantic similarity scoring for Event clustering / merge.

Weights (configurable via settings, defaults match product spec):
  embedding  60%
  entities   20%
  keywords   10%
  time       10%
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Sequence

from app.services.clustering import cosine_similarity

_NORM = re.compile(r"[^\w]+", re.UNICODE)
_STOP = {
    "что", "как", "это", "для", "или", "the", "and", "for", "with", "будет",
    "были", "новый", "новые", "новости",
}


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


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


def _stem(token: str) -> str:
    t = token.lower()
    for suf in ("ами", "ями", "ов", "ей", "ах", "ях", "ом", "ем", "ый", "ая", "ое", "ые"):
        if len(t) > 5 and t.endswith(suf):
            return t[: -len(suf)]
    if len(t) > 4 and t[-1] in "аеиоуыяю":
        return t[:-1]
    return t


def _content_tokens(text: str) -> set[str]:
    toks = {t.lower() for t in re.findall(r"[\w\-]{3,}", text or "", flags=re.UNICODE)}
    return {_stem(t) for t in toks if t not in _STOP and not t.isdigit()}


def _content_overlap(a: str, b: str) -> float:
    left = _content_tokens(a)
    right = _content_tokens(b)
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


@dataclass(frozen=True, slots=True)
class SimilarityBreakdown:
    total: float
    embedding: float
    entities: float
    keywords: float
    time: float


def entity_similarity(a: Sequence[str] | None, b: Sequence[str] | None) -> float:
    left = _entity_tokens(list(a) if a else None)
    right = _entity_tokens(list(b) if b else None)
    if not left and not right:
        return 0.0
    if not left or not right:
        return 0.35
    return len(left & right) / len(left | right)


def keyword_similarity(
    a: Sequence[str] | None,
    b: Sequence[str] | None,
    *,
    text_a: str = "",
    text_b: str = "",
) -> float:
    left = {t.lower() for t in (a or []) if t and len(str(t)) >= 2}
    right = {t.lower() for t in (b or []) if t and len(str(t)) >= 2}
    if not left:
        left = _content_tokens(text_a)
    if not right:
        right = _content_tokens(text_b)
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def time_proximity(
    a: datetime | None,
    b: datetime | None,
    *,
    window_hours: float = 72.0,
) -> float:
    if a is None or b is None:
        return 0.5
    if a.tzinfo is None:
        a = a.replace(tzinfo=timezone.utc)
    if b.tzinfo is None:
        b = b.replace(tzinfo=timezone.utc)
    hours = abs((a - b).total_seconds()) / 3600.0
    if hours >= window_hours:
        return 0.0
    return _clamp01(1.0 - hours / window_hours)


def category_bonus(a: str | None, b: str | None) -> float:
    from app.services.categories import normalize_category

    if not a or not b:
        return 0.0
    return 0.04 if normalize_category(a) == normalize_category(b) else 0.0


def similarity_score(
    *,
    embedding_a: Sequence[float] | None,
    embedding_b: Sequence[float] | None,
    entities_a: Sequence[str] | None = None,
    entities_b: Sequence[str] | None = None,
    keywords_a: Sequence[str] | None = None,
    keywords_b: Sequence[str] | None = None,
    text_a: str = "",
    text_b: str = "",
    time_a: datetime | None = None,
    time_b: datetime | None = None,
    category_a: str | None = None,
    category_b: str | None = None,
    w_embedding: float = 0.60,
    w_entities: float = 0.20,
    w_keywords: float = 0.10,
    w_time: float = 0.10,
    time_window_hours: float = 72.0,
) -> SimilarityBreakdown:
    try:
        emb = (
            float(cosine_similarity(list(embedding_a), list(embedding_b)))
            if embedding_a and embedding_b
            else 0.0
        )
    except Exception:
        emb = 0.0
    emb = _clamp01(emb)

    ent = _clamp01(entity_similarity(entities_a, entities_b))
    kw = _clamp01(keyword_similarity(keywords_a, keywords_b, text_a=text_a, text_b=text_b))
    lex = _clamp01(_content_overlap(text_a, text_b))
    kw = max(kw, lex * 0.85)
    tim = _clamp01(time_proximity(time_a, time_b, window_hours=time_window_hours))

    total = emb * w_embedding + ent * w_entities + kw * w_keywords + tim * w_time
    total = _clamp01(total + category_bonus(category_a, category_b))
    # Strong entity overlap + some lexical signal → same event (paraphrase-safe)
    if ent >= 0.45 and (kw >= 0.18 or emb >= 0.40):
        total = max(total, 0.72)
    if ent >= 0.33 and kw >= 0.28:
        total = max(total, 0.70)
    # Shared brand tokens in text even without explicit entity lists
    shared_tok = _content_tokens(text_a) & _content_tokens(text_b)
    if len(shared_tok) >= 2 and kw >= 0.22 and tim >= 0.4:
        total = max(total, 0.68)
    return SimilarityBreakdown(
        total=round(total, 4),
        embedding=round(emb, 4),
        entities=round(ent, 4),
        keywords=round(kw, 4),
        time=round(tim, 4),
    )


def should_merge(score: SimilarityBreakdown | float, *, threshold: float) -> bool:
    value = score.total if isinstance(score, SimilarityBreakdown) else float(score)
    return value >= float(threshold)
