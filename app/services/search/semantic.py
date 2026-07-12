"""Strict search: period parse → embeddings → overlap filter → LLM relevance."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.models import News
from app.services.ai import create_ai_service
from app.services.ai.usage import log_ai_usage
from app.services.digest.service import NewsService
from app.services.ports import SearchHit
from app.services.search.keyword import KeywordSearch

logger = logging.getLogger(__name__)

_STOP = {
    "что", "как", "про", "для", "или", "это", "было", "были", "новые", "новости",
    "the", "and", "for", "with", "what", "about", "new", "news", "week", "month",
    "сегодня", "неделя", "неделю", "месяц", "месяца", "за", "по", "с",
}

_PERIOD = [
    (re.compile(r"\b(сегодня|today|heute|hoy)\b", re.I), 1),
    (re.compile(r"\b(недел[еиюя]|week|woche|semana)\b", re.I), 7),
    (re.compile(r"\b(месяц[аеу]?|month|monat|mes)\b", re.I), 30),
    (re.compile(r"\b(сутки|24\s*h|day)\b", re.I), 1),
]


def parse_period_days(query: str) -> int:
    for pattern, days in _PERIOD:
        if pattern.search(query or ""):
            return days
    return 30


def significant_tokens(text: str) -> set[str]:
    tokens = {t.lower() for t in re.findall(r"[\w\-]{2,}", text or "", flags=re.UNICODE)}
    return {t for t in tokens if t not in _STOP and not t.isdigit()}


class SemanticSearch:
    """
    Pipeline:
    1) parse time window
    2) embedding candidates
    3) lexical overlap filter (drop Burger King for iPhone queries)
    4) LLM relevance gate + answer (no hallucination)
    """

    def __init__(
        self,
        session: AsyncSession,
        *,
        news_service: NewsService | None = None,
        min_similarity: float = 0.28,
    ) -> None:
        self._session = session
        self._news = news_service or NewsService(session)
        self._keyword = KeywordSearch(session)
        self._ai = create_ai_service()
        self._settings = get_settings()
        self._min_sim = min_similarity

    async def search(self, query: str, *, limit: int = 10) -> list[SearchHit]:
        q = (query or "").strip()
        if not q:
            return []
        days = parse_period_days(q)
        since = datetime.now(timezone.utc) - timedelta(days=days)
        q_tokens = significant_tokens(q)

        semantic = await self._news.semantic_candidates(q, limit=max(limit * 3, 15), since=since)
        filtered: list[SearchHit] = []
        for news, sim in semantic:
            if sim < self._min_sim and not self._token_overlap(q_tokens, news):
                continue
            if q_tokens and not self._token_overlap(q_tokens, news) and sim < 0.45:
                continue
            filtered.append(
                SearchHit(
                    news_id=news.id,
                    score=round(sim * 10, 2),
                    title=news.title,
                    summary=news.summary,
                )
            )
            if len(filtered) >= limit:
                break

        if filtered:
            return filtered

        # keyword fallback still within period
        kw = await self._keyword.search(q, limit=limit * 2)
        out: list[SearchHit] = []
        for hit in kw:
            news = await self._news.get_news(hit.news_id)
            if not news or news.created_at < since:
                continue
            if q_tokens and not self._token_overlap(q_tokens, news):
                continue
            out.append(hit)
            if len(out) >= limit:
                break
        return out

    def _token_overlap(self, q_tokens: set[str], news: News) -> bool:
        if not q_tokens:
            return True
        # Prefer brand/entity tokens; ignore bare numbers like "18" alone
        meaningful = {t for t in q_tokens if not t.isdigit()}
        check = meaningful or q_tokens
        blob_tokens = significant_tokens(f"{news.title} {news.summary} {news.topic or ''}")
        overlap = check & blob_tokens
        if not overlap:
            blob = f"{news.title} {news.summary} {news.topic or ''}".lower()
            if any(t in blob for t in check if len(t) >= 4):
                return True
            return False
        need = 1 if len(check) <= 2 else max(1, len(check) // 2)
        return len(overlap) >= need

    async def search_with_answer(
        self,
        query: str,
        *,
        limit: int = 8,
        empty_message: str | None = None,
    ) -> tuple[str, list[SearchHit], list[News]]:
        empty = empty_message or "По вашему запросу релевантных новостей найдено не было."
        hits = await self.search(query, limit=limit)
        if not hits:
            return empty, [], []

        news_map: dict[int, News] = {}
        contexts: list[tuple[int, str, str]] = []
        for h in hits:
            news = await self._news.get_news(h.news_id)
            if not news:
                continue
            news_map[news.id] = news
            contexts.append((news.id, news.title, news.summary))

        if not contexts:
            return empty, [], []

        if not self._settings.ai_search_synthesis:
            # still apply heuristic relevance
            ans = await self._ai.answer_search(query, contexts)
            used = [news_map[i] for i in ans.used_news_ids if i in news_map]
            if not ans.relevant or not used:
                return empty, [], []
            kept_hits = [h for h in hits if h.news_id in {n.id for n in used}]
            return ans.answer, kept_hits, used

        answer = await self._ai.answer_search(query, contexts)
        await log_ai_usage(
            self._session,
            provider=getattr(self._ai, "provider_name", "unknown"),
            operation="answer_search",
        )
        if not answer.relevant or not answer.used_news_ids:
            return empty, [], []

        used_ids = set(answer.used_news_ids)
        used_news = [news_map[i] for i in answer.used_news_ids if i in news_map]
        kept_hits = [h for h in hits if h.news_id in used_ids]
        return answer.answer, kept_hits, used_news
