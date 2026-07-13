"""Groq-backed AIService implementation."""

from __future__ import annotations

import logging
from typing import Any, Sequence

from app.services.ai.base import (
    PostAnalysisResult,
    SearchAnswer,
    TranslationResult,
)
from app.services.ai.groq_client import GroqClient
from app.services.ai.heuristic import HeuristicAIService
from app.services.categories import normalize_category

logger = logging.getLogger(__name__)

_ANALYZE_SYSTEM = """You analyze ONE Telegram channel post for Briefly (an event news product).
Return ONLY valid JSON with keys:
is_news (bool),
is_advertisement (bool),
title (string, concise headline about THIS post only),
summary (string, 2-4 sentences about THIS post only),
category (ONE of: AI, Technology, Hardware, Software, Science, Business, Politics, Entertainment, Sports, Health, Security, Crypto, Gaming, Other),
topic (string: FULL event sentence for THIS post, e.g. "Destin Daniel Cretton снимет фильм по Наруто" — NEVER a single word),
entities (array of strings: brands/products/people from THIS post only),
keywords (array of short search keywords from THIS post),
importance_score (number 0-10),
why_important (string, short reasons separated by "; "),
reasoning (string, brief why this score),
language (string: ru|en|de|es|other),
reason (string|null — only when is_news=false).

CRITICAL fidelity rules for title/summary/topic:
- Use ONLY facts explicitly present in the message text.
- NEVER invent connections between unrelated franchises, films, games, or brands.
- NEVER write that one work is "based on" / "по" another unless the text says that.
- If the post says a director was hired for a Naruto film — say exactly that. Do NOT mention Spider-Man or any other title not in the text.
- Ignore channel footers, "also read", ads, and unrelated neighboring headlines if they appear in the paste.
- Prefer short, precise summary over creative rewriting.

is_advertisement=true for promo codes, subscribe CTAs, sales spam.
is_news=false for ads, chatter, non-news.
Prefer existing categories. Analyze once — results will be reused.
"""

_SEARCH_SYSTEM = """You are a careful event news assistant for Briefly.
You receive a user query and candidate EVENT snippets with IDs (not raw Telegram posts).
Rules:
1) Use ONLY the provided snippets. Never invent facts.
2) Decide which events are truly relevant to the query entities/topic.
3) Reject ads, off-topic, and random brands that do not match the query.
4) NEVER merge unrelated events into one story (e.g. do not claim a Naruto film is based on Spider-Man).
5) If several events are relevant, summarize them as separate facts — do not invent causal links between them.
6) If NONE are relevant, return JSON:
{"relevant": false, "answer": "По вашему запросу релевантных новостей найдено не было.", "used_ids": []}
7) If some are relevant, return JSON:
{"relevant": true, "answer": "2-6 sentences answering the query using only those events", "used_ids": [ids...]}
Answer language: match the user query language.
Secondary quality check: before relevant=true, verify every used_id matches the query and the answer does not invent cross-event links.
"""

_LANG_NAMES = {
    "ru": "Russian",
    "en": "English",
    "de": "German",
    "es": "Spanish",
}


class GroqAIService:
    provider_name = "groq"

    def __init__(self, client: GroqClient) -> None:
        self._client = client
        self._fallback = HeuristicAIService()

    async def analyze_post(
        self,
        text: str,
        *,
        source_count: int = 1,
        channel_title: str | None = None,
    ) -> PostAnalysisResult:
        clipped = (text or "").strip()[:4000]
        if not clipped:
            return PostAnalysisResult(
                is_news=False,
                is_advertisement=False,
                title="",
                summary="",
                category="Other",
                topic=None,
                reason="empty",
            )
        user = (
            f"channel: {channel_title or 'unknown'}\n"
            f"source_count_hint: {source_count}\n\n"
            f"message:\n{clipped}"
        )
        try:
            data = await self._client.chat_json(system=_ANALYZE_SYSTEM, user=user)
            return _to_analysis(data)
        except Exception:
            logger.exception("Groq analyze_post failed; using heuristic fallback")
            return await self._fallback.analyze_post(
                text,
                source_count=source_count,
                channel_title=channel_title,
            )

    async def analyze_message(self, text: str, *, source_count: int = 1, channel_title: str | None = None):
        return await self.analyze_post(text, source_count=source_count, channel_title=channel_title)

    async def answer_question(
        self,
        query: str,
        contexts: Sequence[tuple[int, str, str]],
    ) -> SearchAnswer:
        if not contexts:
            return SearchAnswer(
                answer="По вашему запросу релевантных новостей найдено не было.",
                used_event_ids=(),
                relevant=False,
            )
        blocks = []
        for event_id, title, summary in contexts[:8]:
            blocks.append(f"[{event_id}] {title}\n{summary}")
        user = (
            f"Query: {query}\n\n"
            "Candidate events (use only these facts; do not invent links between them):\n"
            + "\n\n".join(blocks)
            + "\n\nReturn JSON only."
        )
        try:
            data = await self._client.chat_json(system=_SEARCH_SYSTEM, user=user, temperature=0.1)
            return _to_search_answer(data)
        except Exception:
            logger.exception("Groq answer_question failed; using heuristic fallback")
            return await self._fallback.answer_question(query, contexts)

    async def answer_search(self, query: str, contexts: Sequence[tuple[int, str, str]]):
        return await self.answer_question(query, contexts)

    async def translate(
        self,
        *,
        title: str,
        summary: str,
        target_lang: str,
    ) -> TranslationResult:
        lang = _LANG_NAMES.get(target_lang, target_lang)
        system = (
            f"Translate the event title and summary into {lang}. "
            "Return JSON: {\"title\": \"...\", \"summary\": \"...\"}. "
            "Keep meaning; do not add facts."
        )
        user = f"title: {title}\n\nsummary: {summary}"
        try:
            data = await self._client.chat_json(system=system, user=user, temperature=0.1)
            return TranslationResult(
                title=str(data.get("title") or title).strip()[:512],
                summary=str(data.get("summary") or summary).strip(),
            )
        except Exception:
            logger.exception("Groq translate failed")
            return TranslationResult(title=title, summary=summary)

    async def translate_news(self, *, title: str, summary: str, target_lang: str):
        return await self.translate(title=title, summary=summary, target_lang=target_lang)

    async def detect_language(self, text: str) -> str:
        return await self._fallback.detect_language(text)

    async def close(self) -> None:
        await self._client.close()


def _to_analysis(data: dict[str, Any]) -> PostAnalysisResult:
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
    return PostAnalysisResult(
        is_news=is_news,
        is_advertisement=is_ad,
        title=str(data.get("title") or "").strip()[:512] or "Без заголовка",
        summary=str(data.get("summary") or "").strip(),
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


def _str_list(raw: Any) -> tuple[str, ...]:
    if not isinstance(raw, list):
        return ()
    out: list[str] = []
    for x in raw:
        s = str(x).strip()
        if s and s not in out:
            out.append(s[:128])
    return tuple(out[:20])


def _to_search_answer(data: dict[str, Any]) -> SearchAnswer:
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
            answer=answer
            or "По вашему запросу релевантных новостей найдено не было.",
            used_event_ids=(),
            relevant=False,
        )
    return SearchAnswer(answer=answer, used_event_ids=tuple(ids), relevant=True)
