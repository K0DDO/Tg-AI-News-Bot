"""Strict Event search: entities + period + EventIndex + LLM relevance gate."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import Event, User
from app.services.ai import create_ai_service
from app.services.ai.usage import log_ai_usage
from app.services.embedding import EmbeddingService
from app.services.events.index import EventIndexService
from app.services.events.pipeline import EventPipeline
from app.services.ports import SearchHit
from app.services.preferences import PreferencesService

logger = logging.getLogger(__name__)

_STOP = {
    "что", "как", "про", "для", "или", "это", "было", "были", "новые", "новости",
    "the", "and", "for", "with", "what", "about", "new", "news", "week", "month",
    "сегодня", "неделя", "неделю", "месяц", "месяца", "за", "по", "с", "лучш",
    "лучшие", "нейросети", "happened", "neuen", "nuevo",
    # weak generic nouns that cause false search hits
    "фильм", "фильма", "фильме", "кино", "студия", "режиссер", "режиссёр",
    "новый", "новая", "новое", "день", "дня", "года", "снят", "снимут",
    "будет", "стал", "станет", "уже", "пока", "нет", "есть", "movie", "film",
    "director", "studio", "release",
}

_PERIOD = [
    (re.compile(r"\b(сегодня|today|heute|hoy)\b", re.I), 1),
    (re.compile(r"\b(недел[еиюя]|week|woche|semana)\b", re.I), 7),
    (re.compile(r"\b(месяц[аеу]?|month|monat|mes)\b", re.I), 30),
    (re.compile(r"\b(сутки|24\s*h|day)\b", re.I), 1),
]

_ENTITY_PAT = re.compile(
    r"\b(OpenAI|ChatGPT|GPT-?\d*|Claude|Gemini|NVIDIA|Apple|iPhone(?:\s*\d+\s*Pro)?|"
    r"Google|Microsoft|Cursor|Windows|Linux|Tesla|Meta|Amazon|Intel|AMD|"
    r"Steam(?:\s*Machine)?|Docker|Kubernetes)\b",
    re.I,
)


def parse_period_days(query: str) -> int:
    for pattern, days in _PERIOD:
        if pattern.search(query or ""):
            return days
    return 30


def significant_tokens(text: str) -> set[str]:
    tokens = {t.lower() for t in re.findall(r"[\w\-]{2,}", text or "", flags=re.UNICODE)}
    return {t for t in tokens if t not in _STOP and not t.isdigit()}


def extract_query_entities(query: str) -> list[str]:
    found = [m.group(0).strip() for m in _ENTITY_PAT.finditer(query or "")]
    # dedupe case-insensitive
    out: list[str] = []
    seen: set[str] = set()
    for e in found:
        key = e.lower()
        if key not in seen:
            seen.add(key)
            out.append(e)
    if out:
        return out
    # fallback: meaningful tokens length >= 4
    return [t for t in significant_tokens(query) if len(t) >= 4][:5]


class SearchService:
    """Search works ONLY on Event Index — never raw Telegram posts."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._ai = create_ai_service()
        self._settings = get_settings()
        self._embed = EmbeddingService()
        self._index = EventIndexService(session, self._embed.port)
        self._pipeline = EventPipeline(session, embedding=self._embed.port, ai=self._ai)
        self._prefs = PreferencesService(session)

    async def search(
        self,
        query: str,
        *,
        limit: int = 10,
        user: User | None = None,
    ) -> list[SearchHit]:
        q = (query or "").strip()
        if not q:
            return []
        days = parse_period_days(q)
        since = datetime.now(timezone.utc) - timedelta(days=days)
        q_entities = [e.lower() for e in extract_query_entities(q)]
        q_tokens = significant_tokens(q)

        channel_ids = None
        if user is not None:
            from app.services.preferences import FeedService

            channel_ids = await FeedService(self._session)._user_channel_ids(user.id) or None

        events = await self._index.load_active(since=since, limit=500, channel_ids=channel_ids)
        # If personal scope is empty, fall back to global Event index
        if channel_ids and not events:
            events = await self._index.load_active(since=since, limit=500, channel_ids=None)

        ranked = self._index.semantic_rank(q, events, limit=max(limit * 4, 20), min_sim=0.18)

        filtered: list[SearchHit] = []
        for event, sim in ranked:
            if not self._is_relevant(event, q_entities, q_tokens, sim):
                continue
            filtered.append(
                SearchHit(
                    news_id=event.id,
                    score=round(sim * 10, 2),
                    title=event.title,
                    summary=event.summary,
                )
            )
            if len(filtered) >= limit:
                break
        return filtered

    def _is_relevant(
        self,
        event: Event,
        q_entities: list[str],
        q_tokens: set[str],
        sim: float,
    ) -> bool:
        blob = f"{event.title} {event.summary} {event.topic or ''}".lower()
        ent_blob = " ".join(str(x).lower() for x in (event.entities or []))
        kw_blob = " ".join(str(x).lower() for x in (event.keywords or []))
        full = f"{blob} {ent_blob} {kw_blob}"

        if q_entities:
            # Require at least one query entity to appear in event
            hits = [e for e in q_entities if e in full]
            if not hits:
                # also try tokenized entity parts (iphone, 18, pro → need iphone)
                parts_ok = False
                for e in q_entities:
                    parts = [p for p in re.findall(r"[a-zA-Zа-яА-Я]{3,}", e) if p.lower() not in _STOP]
                    if parts and all(p.lower() in full for p in parts[:2]):
                        parts_ok = True
                        break
                if not parts_ok:
                    return False
            elif len(q_entities) >= 2:
                # Multi-token queries (e.g. «человек-паук») must match more than one weak token
                need = 2 if len(q_entities) <= 3 else max(2, len(q_entities) // 2)
                if len(hits) < need and sim < 0.52:
                    return False

        meaningful = {t for t in q_tokens if not t.isdigit() and len(t) >= 3}
        if meaningful and not q_entities:
            overlap = {t for t in meaningful if t in full}
            need = 1 if len(meaningful) <= 2 else max(1, len(meaningful) // 2)
            if len(overlap) < need and sim < 0.45:
                return False
        return True

    async def search_with_answer(
        self,
        query: str,
        *,
        limit: int = 8,
        empty_message: str | None = None,
        user: User | None = None,
    ) -> tuple[str, list[SearchHit], list[Event]]:
        empty = empty_message or "По вашему запросу релевантных новостей найдено не было."
        hits = await self.search(query, limit=limit, user=user)
        if not hits:
            return empty, [], []

        event_map: dict[int, Event] = {}
        contexts: list[tuple[int, str, str]] = []
        for h in hits:
            event = await self._pipeline.get_event(h.news_id)
            if not event:
                continue
            event_map[event.id] = event
            contexts.append((event.id, event.title, event.summary))

        if not contexts:
            return empty, [], []

        answer = await self._ai.answer_question(query, contexts)
        await log_ai_usage(
            self._session,
            provider=getattr(self._ai, "provider_name", "unknown"),
            operation="answer_question",
        )

        # Secondary quality pass — heuristic re-check
        if answer.relevant and answer.used_event_ids:
            q_entities = [e.lower() for e in extract_query_entities(query)]
            q_tokens = significant_tokens(query)
            kept_ids = []
            for eid in answer.used_event_ids:
                ev = event_map.get(eid)
                if ev and self._is_relevant(ev, q_entities, q_tokens, 1.0):
                    kept_ids.append(eid)
            if not kept_ids:
                return empty, [], []
            used = [event_map[i] for i in kept_ids if i in event_map]
            kept_hits = [h for h in hits if h.news_id in set(kept_ids)]
            text = answer.answer
            if not self._answer_faithful(query, text, used):
                from app.services.ai.heuristic import HeuristicAIService

                safe = await HeuristicAIService().answer_question(
                    query,
                    [(e.id, e.title, e.summary) for e in used],
                )
                if not safe.relevant:
                    return empty, [], []
                text = safe.answer
            return text, kept_hits, used

        if not answer.relevant or not answer.used_event_ids:
            return empty, [], []

        used_ids = set(answer.used_event_ids)
        used_events = [event_map[i] for i in answer.used_event_ids if i in event_map]
        kept_hits = [h for h in hits if h.news_id in used_ids]
        return answer.answer, kept_hits, used_events

    @staticmethod
    def _answer_faithful(query: str, answer: str, events: list[Event]) -> bool:
        """Reject answers that inject distinctive query tokens absent from used events."""
        q_tokens = {t for t in significant_tokens(query) if len(t) >= 5}
        if not q_tokens:
            return True
        blob = " ".join(
            f"{e.title} {e.summary} {e.topic or ''} {' '.join(str(x) for x in (e.entities or []))}"
            for e in events
        ).lower()
        answer_l = (answer or "").lower()
        # Tokens from the query that appear in the answer must also appear in sources
        for tok in q_tokens:
            if tok in answer_l and tok not in blob:
                return False
        return True


# Compat
SemanticSearch = SearchService
