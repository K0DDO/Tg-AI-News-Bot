"""AI provider protocol + shared prompts/parsers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, Sequence

from app.services.categories import ALLOWED_CATEGORIES, normalize_category


@dataclass(frozen=True, slots=True)
class PostAnalysisResult:
    """Single-shot analysis of a Telegram post → Event fields."""

    is_news: bool
    is_advertisement: bool
    title: str
    summary: str
    category: str
    topic: str | None
    entities: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()
    importance_score: float = 0.0
    why_important: str | None = None
    reasoning: str | None = None
    language: str | None = None
    reason: str | None = None


NewsAnalysisResult = PostAnalysisResult


@dataclass(frozen=True, slots=True)
class SearchAnswer:
    answer: str
    used_event_ids: tuple[int, ...] = ()
    relevant: bool = True

    @property
    def used_news_ids(self) -> tuple[int, ...]:
        return self.used_event_ids


@dataclass(frozen=True, slots=True)
class TranslationResult:
    title: str
    summary: str


@dataclass(frozen=True, slots=True)
class CallMeta:
    provider: str = ""
    model: str = ""
    key_fingerprint: str = ""
    latency_ms: int = 0
    tokens_in: int | None = None
    tokens_out: int | None = None
    status: str = "ok"  # ok | error | fallback
    error_code: str = ""
    operation: str = ""


@dataclass(frozen=True, slots=True)
class AnalyzedPost:
    result: PostAnalysisResult
    meta: CallMeta = field(default_factory=CallMeta)


@dataclass(frozen=True, slots=True)
class AnsweredQuestion:
    result: SearchAnswer
    meta: CallMeta = field(default_factory=CallMeta)


@dataclass(frozen=True, slots=True)
class TranslatedText:
    result: TranslationResult
    meta: CallMeta = field(default_factory=CallMeta)


_THEME_LIST = ", ".join(ALLOWED_CATEGORIES)

ANALYZE_SYSTEM = f"""You analyze ONE Telegram channel post for Briefly (an event news product).
Return ONLY valid JSON with keys:
is_news (bool),
is_advertisement (bool),
title (string, concise headline about THIS post only),
summary (string, 2-4 sentences about THIS post only),
category (ONE of: {_THEME_LIST}),
topic (string: FULL event sentence for THIS post — NEVER a single word),
entities (array of strings: brands/products/people from THIS post only),
keywords (array of short search keywords from THIS post),
importance_score (number 0-10),
why_important (string, short reasons separated by "; "),
reasoning (string, brief why this score),
language (string: ru|en|de|es|zh|other),
reason (string|null — only when is_news=false).

CRITICAL fidelity rules for title/summary/topic:
- Use ONLY facts explicitly present in the message text.
- NEVER invent connections between unrelated franchises, films, games, or brands.
- Prefer short, precise summary over creative rewriting.
- Title must name the core event once (no clickbait, no duplicate variants).
- Keep important details (who/what/where) when present in the post.
- If the post is a paraphrase of a known event (same product/action), keep a stable canonical title.
is_advertisement=true for promo codes, subscribe CTAs, sales spam.
is_news=false for ads, chatter, non-news.
"""

SEARCH_SYSTEM = """You are a careful event news assistant for Briefly.
You receive a user query and candidate EVENT snippets with IDs (not raw Telegram posts).
Rules:
1) Use ONLY the provided snippets. Never invent facts.
2) Decide which events are truly relevant to the query entities/topic.
3) Reject ads, off-topic, and random brands that do not match the query.
4) NEVER merge unrelated events into one story.
5) If several snippets describe the SAME event, treat them as one story and mention multiple sources.
6) If NONE are relevant, return JSON:
{"relevant": false, "answer": "По вашему запросу релевантных новостей найдено не было.", "used_ids": []}
7) If some are relevant, return JSON:
{"relevant": true, "answer": "2-6 sentences answering the query using only those events", "used_ids": [ids...]}
Answer language: match the user query language.
"""

LANG_NAMES = {
    "ru": "Russian",
    "en": "English",
    "de": "German",
    "es": "Spanish",
    "zh": "Chinese",
}


class AIProvider(Protocol):
    """Low-level provider used by AIManager (one key / one client)."""

    provider_name: str

    async def classify_news(
        self,
        text: str,
        *,
        source_count: int = 1,
        channel_title: str | None = None,
    ) -> AnalyzedPost:
        ...

    async def summarize_news(
        self,
        text: str,
        *,
        source_count: int = 1,
        channel_title: str | None = None,
    ) -> AnalyzedPost:
        """Same as classify for providers that do one-shot analysis."""
        ...

    async def translate_news(
        self,
        *,
        title: str,
        summary: str,
        target_lang: str,
    ) -> TranslatedText:
        ...

    async def search_answer(
        self,
        query: str,
        contexts: Sequence[tuple[int, str, str]],
    ) -> AnsweredQuestion:
        ...

    async def merge_news(
        self,
        query: str,
        contexts: Sequence[tuple[int, str, str]],
    ) -> AnsweredQuestion:
        ...

    async def analyze_relations(
        self,
        query: str,
        contexts: Sequence[tuple[int, str, str]],
    ) -> AnsweredQuestion:
        ...

    async def close(self) -> None:
        ...


class AIService(Protocol):
    """Provider-agnostic AI interface used by the rest of the app."""

    provider_name: str

    async def analyze_post(
        self,
        text: str,
        *,
        source_count: int = 1,
        channel_title: str | None = None,
    ) -> PostAnalysisResult:
        ...

    async def answer_question(
        self,
        query: str,
        contexts: Sequence[tuple[int, str, str]],
    ) -> SearchAnswer:
        ...

    async def translate(
        self,
        *,
        title: str,
        summary: str,
        target_lang: str,
    ) -> TranslationResult:
        ...

    async def detect_language(self, text: str) -> str:
        ...

    async def close(self) -> None:
        ...

    async def analyze_message(
        self,
        text: str,
        *,
        source_count: int = 1,
        channel_title: str | None = None,
    ) -> PostAnalysisResult:
        return await self.analyze_post(
            text, source_count=source_count, channel_title=channel_title
        )

    async def answer_search(
        self,
        query: str,
        contexts: Sequence[tuple[int, str, str]],
    ) -> SearchAnswer:
        return await self.answer_question(query, contexts)

    async def translate_news(
        self,
        *,
        title: str,
        summary: str,
        target_lang: str,
    ) -> TranslationResult:
        return await self.translate(title=title, summary=summary, target_lang=target_lang)


def to_analysis(data: dict[str, Any]) -> PostAnalysisResult:
    category = normalize_category(str(data.get("category") or "Other"))
    try:
        score = float(data.get("importance_score", 0))
    except (TypeError, ValueError):
        score = 0.0
    score = max(0.0, min(10.0, score))
    topic = str(data.get("topic") or "").strip()[:512] or None
    why = str(data.get("why_important") or "").strip() or None
    reasoning = str(data.get("reasoning") or why or "").strip() or None
    entities = _str_list(data.get("entities"))
    keywords = _str_list(data.get("keywords")) or entities
    reason = data.get("reason")
    is_ad = bool(data.get("is_advertisement", False))
    is_news = bool(data.get("is_news", False)) and not is_ad
    title = str(data.get("title") or "").strip()[:512]
    summary = str(data.get("summary") or "").strip()
    # Quality gate: empty / too short title → mark weak for heuristic fallback upstream
    if len(title) < 8:
        title = title or "Без заголовка"
        if is_news and not summary:
            is_news = False
            reason = reason or "low_quality_ai"
    return PostAnalysisResult(
        is_news=is_news,
        is_advertisement=is_ad,
        title=title or "Без заголовка",
        summary=summary,
        category=category,
        topic=topic,
        entities=entities,
        keywords=keywords,
        importance_score=round(score, 2),
        why_important=why,
        reasoning=reasoning,
        language=str(data.get("language") or "").strip()[:16] or None,
        reason=str(reason) if reason else ("advertisement" if is_ad else None),
    )


def to_search_answer(data: dict[str, Any]) -> SearchAnswer:
    relevant = bool(data.get("relevant", True))
    answer = str(data.get("answer") or "").strip()
    raw_ids = data.get("used_ids") or data.get("used_event_ids") or data.get("used_news_ids") or []
    ids: list[int] = []
    for x in raw_ids:
        try:
            ids.append(int(x))
        except (TypeError, ValueError):
            continue
    if not relevant or not ids:
        return SearchAnswer(
            answer=answer or "По вашему запросу релевантных новостей найдено не было.",
            used_event_ids=(),
            relevant=False,
        )
    return SearchAnswer(answer=answer, used_event_ids=tuple(ids), relevant=True)


def _str_list(raw: Any) -> tuple[str, ...]:
    if not isinstance(raw, list):
        return ()
    out: list[str] = []
    for x in raw:
        s = str(x).strip()
        if s and s not in out:
            out.append(s[:128])
    return tuple(out[:20])
