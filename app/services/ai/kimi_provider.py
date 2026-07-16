"""Kimi (Moonshot) provider — heavy search / relations / merge."""

from __future__ import annotations

from typing import Sequence

from app.services.ai.base import (
    ANALYZE_SYSTEM,
    LANG_NAMES,
    SEARCH_SYSTEM,
    AnalyzedPost,
    AnsweredQuestion,
    CallMeta,
    SearchAnswer,
    TranslatedText,
    TranslationResult,
    to_analysis,
    to_search_answer,
)
from app.services.ai.openai_compat import OpenAICompatClient

_RELATIONS_SYSTEM = SEARCH_SYSTEM + """
Extra: focus on entity relationships and how events connect WITHOUT inventing links.
Prefer listing related facts separately over claiming causation.
"""


class KimiProvider:
    provider_name = "kimi"

    def __init__(self, client: OpenAICompatClient) -> None:
        self._client = client

    async def classify_news(
        self,
        text: str,
        *,
        source_count: int = 1,
        channel_title: str | None = None,
    ) -> AnalyzedPost:
        return await self._analyze(text, source_count=source_count, channel_title=channel_title)

    async def summarize_news(
        self,
        text: str,
        *,
        source_count: int = 1,
        channel_title: str | None = None,
    ) -> AnalyzedPost:
        return await self._analyze(text, source_count=source_count, channel_title=channel_title)

    async def _analyze(
        self,
        text: str,
        *,
        source_count: int = 1,
        channel_title: str | None = None,
    ) -> AnalyzedPost:
        clipped = (text or "").strip()[:6000]
        if not clipped:
            empty = to_analysis(
                {
                    "is_news": False,
                    "is_advertisement": False,
                    "title": "",
                    "summary": "",
                    "category": "technology",
                    "reason": "empty",
                }
            )
            return AnalyzedPost(result=empty, meta=CallMeta(provider="kimi", status="ok", operation="analyze"))
        user = (
            f"channel: {channel_title or 'unknown'}\n"
            f"source_count_hint: {source_count}\n\n"
            f"message:\n{clipped}"
        )
        data, chat = await self._client.chat_json(system=ANALYZE_SYSTEM, user=user)
        return AnalyzedPost(
            result=to_analysis(data),
            meta=CallMeta(
                provider="kimi",
                model=chat.model,
                key_fingerprint=chat.key_fingerprint,
                latency_ms=chat.latency_ms,
                tokens_in=chat.tokens_in,
                tokens_out=chat.tokens_out,
                status="ok",
                operation="analyze",
            ),
        )

    async def translate_news(
        self,
        *,
        title: str,
        summary: str,
        target_lang: str,
    ) -> TranslatedText:
        lang = LANG_NAMES.get(target_lang, target_lang)
        system = (
            f"Translate the event title and summary into {lang}. "
            'Return JSON: {"title": "...", "summary": "..."}. '
            "Keep meaning; do not add facts."
        )
        user = f"title: {title}\n\nsummary: {summary}"
        data, chat = await self._client.chat_json(system=system, user=user, temperature=0.1)
        return TranslatedText(
            result=TranslationResult(
                title=str(data.get("title") or title).strip()[:512],
                summary=str(data.get("summary") or summary).strip(),
            ),
            meta=CallMeta(
                provider="kimi",
                model=chat.model,
                key_fingerprint=chat.key_fingerprint,
                latency_ms=chat.latency_ms,
                tokens_in=chat.tokens_in,
                tokens_out=chat.tokens_out,
                status="ok",
                operation="translate",
            ),
        )

    async def search_answer(
        self,
        query: str,
        contexts: Sequence[tuple[int, str, str]],
    ) -> AnsweredQuestion:
        return await self._search(query, contexts, system=SEARCH_SYSTEM, operation="search")

    async def merge_news(
        self,
        query: str,
        contexts: Sequence[tuple[int, str, str]],
    ) -> AnsweredQuestion:
        return await self._search(query, contexts, system=SEARCH_SYSTEM, operation="merge")

    async def analyze_relations(
        self,
        query: str,
        contexts: Sequence[tuple[int, str, str]],
    ) -> AnsweredQuestion:
        return await self._search(
            query, contexts, system=_RELATIONS_SYSTEM, operation="relations"
        )

    async def _search(
        self,
        query: str,
        contexts: Sequence[tuple[int, str, str]],
        *,
        system: str,
        operation: str,
    ) -> AnsweredQuestion:
        if not contexts:
            return AnsweredQuestion(
                result=SearchAnswer(
                    answer="По вашему запросу релевантных новостей найдено не было.",
                    used_event_ids=(),
                    relevant=False,
                ),
                meta=CallMeta(provider="kimi", status="ok", operation=operation),
            )
        blocks = [f"[{eid}] {title}\n{summary}" for eid, title, summary in contexts[:8]]
        user = (
            f"Query: {query}\n\n"
            "Candidate events (use only these facts; do not invent links between them):\n"
            + "\n\n".join(blocks)
            + "\n\nReturn JSON only."
        )
        data, chat = await self._client.chat_json(system=system, user=user, temperature=0.1)
        return AnsweredQuestion(
            result=to_search_answer(data),
            meta=CallMeta(
                provider="kimi",
                model=chat.model,
                key_fingerprint=chat.key_fingerprint,
                latency_ms=chat.latency_ms,
                tokens_in=chat.tokens_in,
                tokens_out=chat.tokens_out,
                status="ok",
                operation=operation,
            ),
        )

    async def close(self) -> None:
        await self._client.close()
