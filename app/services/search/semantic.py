"""Knowledge Graph search — Events via Nodes, not Telegram posts.

Pipeline:
  query → intent → entity link → graph expand → events → multi-rank →
  secondary filter → AI context → LLM answer (LLM never searches).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import Event, User
from app.services.ai import create_ai_service
from app.services.ai.usage import log_ai_usage
from app.services.embedding import EmbeddingService
from app.services.events.index import EventIndexService
from app.services.events.pipeline import EventPipeline
from app.services.knowledge.intent import SearchIntent, detect_intent, related_questions
from app.services.knowledge.ranking import (
    DEEP_SECONDARY_THRESHOLD,
    SECONDARY_THRESHOLD,
    rank_event,
)
from app.services.knowledge.service import KnowledgeGraphService, RankedEvent
from app.services.ports import SearchHit
from app.services.preferences import PreferencesService

logger = logging.getLogger(__name__)

_STOP = {
    "что", "как", "про", "для", "или", "это", "было", "были", "новые", "новости",
    "the", "and", "for", "with", "what", "about", "new", "news", "week", "month",
    "сегодня", "неделя", "неделю", "месяц", "месяца", "за", "по", "с", "лучш",
    "лучшие", "нейросети", "happened", "neuen", "nuevo", "почему", "why",
}


def parse_period_days(query: str) -> int:
    intent = detect_intent(query)
    return intent.period_days or 30


def normalize_search_query(query: str) -> str:
    """ё→е, collapse whitespace — keeps ranking stable across RU variants."""
    q = (query or "").replace("ё", "е").replace("Ё", "Е")
    q = re.sub(r"\s+", " ", q).strip()
    return q


def significant_tokens(text: str) -> set[str]:
    tokens = {t.lower() for t in re.findall(r"[\w\-]{2,}", text or "", flags=re.UNICODE)}
    return {t for t in tokens if t not in _STOP and not t.isdigit()}


def extract_query_entities(query: str) -> list[str]:
    """Compat helper — prefer KnowledgeGraphService.resolve_query_nodes in new code."""
    from app.services.knowledge.aliases import ALIAS_MAP

    q = (query or "").lower()
    out: list[str] = []
    seen: set[str] = set()
    for alias, (name, _t, _c) in sorted(ALIAS_MAP.items(), key=lambda x: -len(x[0])):
        if len(alias) >= 3 and alias in q and name.lower() not in seen:
            seen.add(name.lower())
            out.append(name)
    if out:
        return out
    return [t for t in significant_tokens(query) if len(t) >= 4][:5]


@dataclass
class SearchResult:
    answer: str
    hits: list[SearchHit]
    events: list[Event]
    external_count: int = 0
    explanations: dict[int, list[str]] = field(default_factory=dict)
    related_questions: list[str] = field(default_factory=list)
    intent: str = "news"
    matched_nodes: list[str] = field(default_factory=list)
    deep: bool = False


class SearchService:
    """Search works on Knowledge Graph + Event Index — never raw Telegram posts."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._ai = create_ai_service()
        self._settings = get_settings()
        self._embed = EmbeddingService()
        self._index = EventIndexService(session, self._embed.port)
        self._pipeline = EventPipeline(session, embedding=self._embed.port, ai=self._ai)
        self._prefs = PreferencesService(session)
        self._kg = KnowledgeGraphService(session)

    async def search(
        self,
        query: str,
        *,
        limit: int = 10,
        user: User | None = None,
        scope: str = "auto",
        deep: bool = False,
    ) -> list[SearchHit]:
        ranked = await self.search_ranked(
            query, limit=limit, user=user, scope=scope, deep=deep
        )
        return [
            SearchHit(
                news_id=r.event.id,
                score=round(r.score * 10, 2),
                title=r.event.title,
                summary=r.event.summary,
            )
            for r in ranked
        ]

    async def search_ranked(
        self,
        query: str,
        *,
        limit: int = 10,
        user: User | None = None,
        scope: str = "auto",
        deep: bool = False,
        seed_event_ids: list[int] | None = None,
    ) -> list[RankedEvent]:
        from app.services.events.merge import is_near_duplicate

        q = normalize_search_query(query)
        if not q:
            return []

        intent = detect_intent(q, deep=deep)
        days = intent.period_days or 30
        if deep or intent.intent == SearchIntent.DEEP:
            days = max(days, 60)
            deep = True
            limit = max(limit, 12)
        since = datetime.now(timezone.utc) - timedelta(days=days)

        channel_ids = None
        enabled_themes: list[str] | None = None
        theme_weights: dict[str, int] = {}
        if user is not None and scope in ("auto", "user"):
            from app.services.preferences import FeedService

            channel_ids = await FeedService(self._session)._user_channel_ids(user.id) or None
            us = await self._prefs.get_or_create(user)
            enabled_themes = list(us.enabled_categories or [])
            theme_weights = dict(us.theme_weights or {})
        if scope == "global":
            channel_ids = None

        seed_nodes = await self._kg.resolve_query_nodes(q)
        seed_ids = [n.id for n in seed_nodes]
        if deep and seed_event_ids:
            for eid in seed_event_ids[:12]:
                for n in await self._kg.nodes_for_event(int(eid)):
                    if n.id not in seed_ids:
                        seed_ids.append(n.id)
                        seed_nodes.append(n)
        expanded = await self._kg.expand_nodes(seed_ids, max_extra=24 if deep else 10)
        node_distance = {n.id: dist for n, dist in expanded}
        all_node_ids = list(node_distance.keys())

        graph_event_ids = await self._kg.event_ids_for_nodes(all_node_ids, limit=600 if deep else 300)
        events = await self._index.load_active(
            since=since, limit=600 if deep else 500, channel_ids=channel_ids
        )

        if channel_ids is not None:
            allowed = await self._index_allowed(channel_ids)
            if allowed is not None:
                events = [e for e in events if e.id in allowed]
                graph_event_ids &= allowed

        by_id = {e.id: e for e in events}
        if seed_event_ids:
            for eid in seed_event_ids:
                if int(eid) in by_id:
                    continue
                ev = await self._pipeline.get_event(int(eid))
                if ev:
                    by_id[ev.id] = ev

        candidate_ids: set[int] = set()
        for eid in graph_event_ids:
            if eid in by_id:
                candidate_ids.add(eid)
        if seed_event_ids:
            candidate_ids |= {int(i) for i in seed_event_ids if int(i) in by_id}

        q_emb = self._embed.embed(q)
        min_sim = 0.12 if deep else 0.16
        if (
            intent.intent in (SearchIntent.RECOMMENDATION, SearchIntent.QA, SearchIntent.DEEP)
            or deep
            or not candidate_ids
        ):
            for event, sim in self._index.semantic_rank(
                q, list(by_id.values()), limit=60 if deep else 40, min_sim=min_sim
            ):
                if sim >= min_sim:
                    candidate_ids.add(event.id)
                    by_id[event.id] = event

        personal_map: dict[int, float] = {}
        if user is not None:
            personal_map = await self._personal_scores(user.id, list(candidate_ids))

        seed_set = {int(i) for i in (seed_event_ids or [])}
        event_nodes_cache: dict[int, list] = {}
        ranked: list[RankedEvent] = []
        for eid in candidate_ids:
            event = by_id.get(eid)
            if not event:
                continue
            nodes = event_nodes_cache.get(eid)
            if nodes is None:
                nodes = await self._kg.nodes_for_event(eid)
                event_nodes_cache[eid] = nodes
            matched = [n.name for n in nodes if n.id in node_distance]
            dist = 9
            for n in nodes:
                if n.id in node_distance:
                    dist = min(dist, node_distance[n.id])
            if not matched and seed_nodes:
                dist = 2
            if eid in seed_set:
                dist = 0
            re = rank_event(
                event,
                query_embedding=q_emb,
                distance=dist if matched or not seed_nodes or eid in seed_set else 2,
                matched_nodes=matched or [n.name for n in seed_nodes[:2]],
                personal=personal_map.get(eid, 0.0),
                via_graph=bool(matched) or eid in seed_set,
            )
            if intent.intent == SearchIntent.TIMELINE:
                re.score = 0.55 * re.freshness + 0.45 * re.score
            elif intent.intent == SearchIntent.ENTITY and matched:
                re.score = min(1.0, re.score + 0.08)
            elif intent.intent == SearchIntent.RECOMMENDATION:
                re.score = 0.5 * re.score + 0.3 * re.importance + 0.2 * re.personal
            if deep and eid in seed_set:
                re.score = min(1.0, re.score + 0.12)
                re.explanation = [*re.explanation, "уточнено Deep Search"]
            # ~30% personalization: theme weights + personal_score
            if user is not None:
                from app.services.categories import normalize_category

                theme = normalize_category(event.category)
                w = float(theme_weights.get(theme, 3))
                theme_factor = max(0.0, min(1.0, w / 5.0))
                if enabled_themes is not None and enabled_themes and theme not in enabled_themes:
                    theme_factor *= 0.35
                pers = float(personal_map.get(eid, 0.0))
                personalization = 0.55 * theme_factor + 0.45 * pers
                re.score = min(1.0, 0.70 * re.score + 0.30 * personalization)
            ranked.append(re)

        ranked.sort(key=lambda r: r.score, reverse=True)
        thr = DEEP_SECONDARY_THRESHOLD if deep else SECONDARY_THRESHOLD
        filtered: list[RankedEvent] = []
        for r in ranked:
            if r.score < thr:
                continue
            if seed_nodes and not any(n.name in r.matched_nodes for n in seed_nodes) and not any(
                n.name in (r.matched_nodes or []) for n, d in expanded if d <= 1
            ):
                if intent.intent not in (
                    SearchIntent.QA,
                    SearchIntent.RECOMMENDATION,
                    SearchIntent.DEEP,
                ) and not deep:
                    if r.semantic < 0.42:
                        continue
            blob = f"{r.event.title} {r.event.summary}"
            if any(is_near_duplicate(blob, f"{x.event.title} {x.event.summary}") for x in filtered):
                continue
            filtered.append(r)
            if len(filtered) >= limit:
                break
        return filtered

    async def _index_allowed(self, channel_ids: list[int]) -> set[int] | None:
        from app.services.preferences import FeedService

        return await FeedService(self._session)._event_ids_for_channels(channel_ids)

    async def _personal_scores(self, user_id: int, event_ids: list[int]) -> dict[int, float]:
        if not event_ids:
            return {}
        from sqlalchemy import select

        from app.models import UserEventState

        result = await self._session.execute(
            select(UserEventState).where(
                UserEventState.user_id == user_id,
                UserEventState.event_id.in_(event_ids[:200]),
            )
        )
        out: dict[int, float] = {}
        for st in result.scalars().all():
            # normalize personal_score roughly to 0..1
            out[st.event_id] = max(0.0, min(1.0, (float(st.personal_score or 0) + 2) / 6.0))
        return out

    async def search_with_answer(
        self,
        query: str,
        *,
        limit: int = 8,
        empty_message: str | None = None,
        user: User | None = None,
        include_external: bool = False,
        deep: bool = False,
        lang: str = "ru",
        seed_event_ids: list[int] | None = None,
    ) -> tuple[str, list[SearchHit], list[Event], int]:
        """Backward-compatible tuple API."""
        result = await self.search_full(
            query,
            limit=limit,
            empty_message=empty_message,
            user=user,
            include_external=include_external,
            deep=deep,
            lang=lang,
            seed_event_ids=seed_event_ids,
        )
        return result.answer, result.hits, result.events, result.external_count

    async def search_full(
        self,
        query: str,
        *,
        limit: int = 8,
        empty_message: str | None = None,
        user: User | None = None,
        include_external: bool = False,
        deep: bool = False,
        lang: str = "ru",
        seed_event_ids: list[int] | None = None,
    ) -> SearchResult:
        empty = empty_message or "По вашему запросу релевантных новостей найдено не было."
        query = normalize_search_query(query)
        intent = detect_intent(query, deep=deep)
        scope = "global" if include_external or user is None else "user"
        ranked = await self.search_ranked(
            query,
            limit=limit,
            user=user,
            scope=scope,
            deep=deep or intent.intent == SearchIntent.DEEP,
            seed_event_ids=seed_event_ids,
        )

        external_count = 0
        if user is not None and not include_external:
            user_ids = {r.event.id for r in ranked}
            global_ranked = await self.search_ranked(
                query,
                limit=limit * 2,
                user=user,
                scope="global",
                deep=deep,
                seed_event_ids=seed_event_ids,
            )
            external_count = sum(1 for r in global_ranked if r.event.id not in user_ids)

        seed_nodes = await self._kg.resolve_query_nodes(query)
        node_names = [n.name for n in seed_nodes]
        expanded = await self._kg.expand_nodes([n.id for n in seed_nodes], max_extra=8)
        for n, _d in expanded:
            if n.name not in node_names:
                node_names.append(n.name)

        if not ranked:
            return SearchResult(
                answer=empty,
                hits=[],
                events=[],
                external_count=external_count,
                intent=intent.intent.value,
                matched_nodes=node_names,
                related_questions=related_questions(query, node_names, lang=lang),
                deep=deep,
            )

        explanations = {r.event.id: r.explanation for r in ranked}
        event_map = {r.event.id: r.event for r in ranked}

        # AI context: Event fields + KG relations — never raw posts
        contexts: list[tuple[int, str, str]] = []
        for r in ranked:
            ev = r.event
            nodes = await self._kg.nodes_for_event(ev.id)
            rel = ", ".join(n.name for n in nodes[:8])
            timeline = ""
            if deep and ev.timeline:
                try:
                    parts = []
                    for entry in (ev.timeline or [])[-5:]:
                        if isinstance(entry, dict):
                            parts.append(str(entry.get("text") or entry.get("kind") or ""))
                    timeline = " | ".join(p for p in parts if p)
                except Exception:
                    timeline = ""
            summary = ev.summary
            if rel:
                summary = f"{summary}\nKG: {rel}"
            if timeline:
                summary = f"{summary}\nTimeline: {timeline}"
            if ev.why_important:
                summary = f"{summary}\nWhy: {ev.why_important}"
            contexts.append((ev.id, ev.title, summary))

        answer = await self._ai.answer_question(query, contexts)
        await log_ai_usage(
            self._session,
            provider=getattr(self._ai, "provider_name", "unknown"),
            operation="answer_question",
        )

        hits = [
            SearchHit(
                news_id=r.event.id,
                score=round(r.score * 10, 2),
                title=r.event.title,
                summary=r.event.summary,
            )
            for r in ranked
        ]

        if answer.relevant and answer.used_event_ids:
            used_ids = [i for i in answer.used_event_ids if i in event_map]
            if not used_ids:
                return SearchResult(
                    answer=empty,
                    hits=[],
                    events=[],
                    external_count=external_count,
                    intent=intent.intent.value,
                    matched_nodes=node_names,
                    related_questions=related_questions(query, node_names, lang=lang),
                    deep=deep,
                )
            used = [event_map[i] for i in used_ids]
            kept_hits = [h for h in hits if h.news_id in set(used_ids)]
            text = answer.answer
            if not self._answer_faithful(query, text, used):
                from app.services.ai.heuristic import HeuristicAIService

                safe = await HeuristicAIService().answer_question(
                    query,
                    [(e.id, e.title, e.summary) for e in used],
                )
                if not safe.relevant:
                    return SearchResult(
                        answer=empty,
                        hits=[],
                        events=[],
                        external_count=external_count,
                        intent=intent.intent.value,
                        matched_nodes=node_names,
                        deep=deep,
                    )
                text = safe.answer
            return SearchResult(
                answer=text,
                hits=kept_hits,
                events=used,
                external_count=external_count,
                explanations={i: explanations.get(i, []) for i in used_ids},
                related_questions=related_questions(query, node_names, lang=lang),
                intent=intent.intent.value,
                matched_nodes=node_names,
                deep=deep,
            )

        if not answer.relevant or not answer.used_event_ids:
            return SearchResult(
                answer=empty,
                hits=[],
                events=[],
                external_count=external_count,
                intent=intent.intent.value,
                matched_nodes=node_names,
                related_questions=related_questions(query, node_names, lang=lang),
                deep=deep,
            )

        used_ids = set(answer.used_event_ids)
        used_events = [event_map[i] for i in answer.used_event_ids if i in event_map]
        kept_hits = [h for h in hits if h.news_id in used_ids]
        return SearchResult(
            answer=answer.answer,
            hits=kept_hits,
            events=used_events,
            external_count=external_count,
            explanations={i: explanations.get(i, []) for i in used_ids},
            related_questions=related_questions(query, node_names, lang=lang),
            intent=intent.intent.value,
            matched_nodes=node_names,
            deep=deep,
        )

    @staticmethod
    def _answer_faithful(query: str, answer: str, events: list[Event]) -> bool:
        q_tokens = {t for t in significant_tokens(query) if len(t) >= 5}
        if not q_tokens:
            return True
        blob = " ".join(
            f"{e.title} {e.summary} {e.topic or ''} {' '.join(str(x) for x in (e.entities or []))}"
            for e in events
        ).lower()
        answer_l = (answer or "").lower()
        for tok in q_tokens:
            if tok in answer_l and tok not in blob:
                return False
        return True

    def _is_relevant(
        self,
        event: Event,
        q_entities: list[str],
        q_tokens: set[str],
        sim: float,
    ) -> bool:
        """Compat relevance gate (used by tests / secondary checks)."""
        blob = f"{event.title} {event.summary} {event.topic or ''}".lower()
        ent_blob = " ".join(str(x).lower() for x in (event.entities or []))
        kw_blob = " ".join(str(x).lower() for x in (event.keywords or []))
        full = f"{blob} {ent_blob} {kw_blob}"
        if q_entities:
            hits = [e for e in q_entities if e.lower() in full]
            if not hits:
                return False
        meaningful = {t for t in q_tokens if not t.isdigit() and len(t) >= 3}
        if meaningful and not q_entities:
            overlap = {t for t in meaningful if t in full}
            need = 1 if len(meaningful) <= 2 else max(1, len(meaningful) // 2)
            if len(overlap) < need and sim < 0.45:
                return False
        return True


# Compat
SemanticSearch = SearchService
