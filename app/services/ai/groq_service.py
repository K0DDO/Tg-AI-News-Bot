"""Groq-backed AIService implementation."""

from __future__ import annotations

import logging
from typing import Any, Sequence

from app.services.ai.base import (
    ALLOWED_CATEGORIES,
    NewsAnalysisResult,
    SearchAnswer,
    TranslationResult,
)
from app.services.ai.groq_client import GroqClient
from app.services.ai.heuristic import HeuristicAIService

logger = logging.getLogger(__name__)

_ANALYZE_SYSTEM = """You analyze Telegram channel posts for a news product called Briefly.
Return ONLY valid JSON with keys:
is_news (bool),
title (string, concise headline in the SAME language as the source when possible),
summary (string, 2-4 sentences),
category (ONE of: AI, Technology, Hardware, Software, Science, Business, Other),
topic (string, short entity/topic name e.g. "NVIDIA", "iPhone 18", "OpenAI" — not a full sentence),
importance_score (number 0-10),
why_important (string, 1-3 short bullet-like reasons separated by "; "),
reason (string|null — only when is_news=false).

Prefer existing category values. Only invent a new category if truly necessary (rare).
is_news=false for ads, promo codes, subscribe CTAs, spam, personal chatter.
"""

_SEARCH_SYSTEM = """You are a careful news assistant for Briefly.
You receive a user query and candidate news snippets with IDs.
Rules:
1) Use ONLY the provided snippets. Never invent facts.
2) First decide which candidates are truly relevant to the query.
3) If NONE are relevant, return JSON:
{"relevant": false, "answer": "По вашему запросу релевантных новостей найдено не было.", "used_ids": []}
4) If some are relevant, return JSON:
{"relevant": true, "answer": "2-6 sentences answering the query", "used_ids": [ids...]}
Answer language: match the user query language.
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

    async def analyze_message(
        self,
        text: str,
        *,
        source_count: int = 1,
        channel_title: str | None = None,
    ) -> NewsAnalysisResult:
        clipped = (text or "").strip()[:4000]
        if not clipped:
            return NewsAnalysisResult(
                is_news=False,
                title="",
                summary="",
                category="Other",
                importance_score=0.0,
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
            logger.exception("Groq analyze_message failed; using heuristic fallback")
            return await self._fallback.analyze_message(
                text,
                source_count=source_count,
                channel_title=channel_title,
            )

    async def answer_search(
        self,
        query: str,
        contexts: Sequence[tuple[int, str, str]],
    ) -> SearchAnswer:
        if not contexts:
            return SearchAnswer(
                answer="По вашему запросу релевантных новостей найдено не было.",
                used_news_ids=(),
                relevant=False,
            )
        blocks = []
        for news_id, title, summary in contexts[:8]:
            blocks.append(f"[{news_id}] {title}\n{summary}")
        user = f"Query: {query}\n\nCandidates:\n" + "\n\n".join(blocks)
        try:
            data = await self._client.chat_json(system=_SEARCH_SYSTEM, user=user, temperature=0.1)
            return _to_search_answer(data)
        except Exception:
            logger.exception("Groq answer_search failed; using heuristic fallback")
            return await self._fallback.answer_search(query, contexts)

    async def translate_news(
        self,
        *,
        title: str,
        summary: str,
        target_lang: str,
    ) -> TranslationResult:
        lang = _LANG_NAMES.get(target_lang, target_lang)
        system = (
            f"Translate the news title and summary into {lang}. "
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

    async def close(self) -> None:
        await self._client.close()


def _to_analysis(data: dict[str, Any]) -> NewsAnalysisResult:
    category = str(data.get("category") or "Other").strip()
    if category not in ALLOWED_CATEGORIES:
        # allow limited custom categories but keep short
        if len(category) > 32 or not category:
            category = "Other"
    try:
        score = float(data.get("importance_score", 0))
    except (TypeError, ValueError):
        score = 0.0
    score = max(0.0, min(10.0, score))
    topic = str(data.get("topic") or "").strip()[:128] or None
    why = str(data.get("why_important") or "").strip() or None
    reason = data.get("reason")
    return NewsAnalysisResult(
        is_news=bool(data.get("is_news", False)),
        title=str(data.get("title") or "").strip()[:512] or "Без заголовка",
        summary=str(data.get("summary") or "").strip(),
        category=category,
        importance_score=round(score, 2),
        reason=str(reason) if reason else None,
        topic=topic,
        why_important=why,
    )


def _to_search_answer(data: dict[str, Any]) -> SearchAnswer:
    relevant = bool(data.get("relevant", True))
    answer = str(data.get("answer") or "").strip()
    raw_ids = data.get("used_ids") or data.get("used_news_ids") or []
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
            used_news_ids=(),
            relevant=False,
        )
    return SearchAnswer(answer=answer, used_news_ids=tuple(ids), relevant=True)
