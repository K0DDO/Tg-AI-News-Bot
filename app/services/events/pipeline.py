"""
Event pipeline — analyze once, reuse many times.

TelegramPost → detect → (one AI analyze_post) → embed → merge/create Event → timeline → Brief
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.models import Event, EventSource, Message, MessageStatus
from app.services.ai import AIService, create_ai_service
from app.services.ai.usage import log_ai_usage
from app.services.clustering import cosine_similarity
from app.services.detection import AdvertisementDetectionService, NewsDetectionService
from app.services.embedding import EmbeddingService
from app.services.events.merge import EventMergeService, light_entities_from_text
from app.services.events.timeline import TimelineService, make_entry
from app.services.ports import ClusterCandidate, EmbeddingPort, ScorerPort
from app.services.scoring import ImportanceScorer
from app.utils.relative_dates import resolve_relative_dates
from app.utils.text_clean import strip_at_mentions

logger = logging.getLogger(__name__)

SIGNIFICANT_SOURCES_DELTA = 5


@dataclass(slots=True)
class ProcessResult:
    event: Event | None
    action: str  # filtered | ad | merged | created

    @property
    def news(self) -> Event | None:
        return self.event


class EventPipeline:
    """
    Cost rule:
    - Full AI analyze_post ONLY on create (and rare significant re-analyze).
    - Merge path: attach source + timeline + rescore — NO LLM.
    """

    def __init__(
        self,
        session: AsyncSession,
        *,
        embedding: EmbeddingPort | None = None,
        ai: AIService | None = None,
        scorer: ScorerPort | None = None,
    ) -> None:
        settings = get_settings()
        self._session = session
        self._embed_svc = EmbeddingService(embedding)
        self._embedding = self._embed_svc.port
        self._ai = ai or create_ai_service()
        self._scorer = scorer or ImportanceScorer()
        self._news_det = NewsDetectionService()
        self._ad_det = AdvertisementDetectionService()
        self._merge = EventMergeService(self._embedding, threshold=settings.cluster_similarity_threshold)
        self._timeline = TimelineService()
        self._lookback_hours = settings.cluster_lookback_hours

    async def process_post(
        self,
        message: Message,
        *,
        channel_title: str | None = None,
        channel_username: str | None = None,
    ) -> ProcessResult:
        # 1) Cheap rule filter
        reject = self._news_det.rule_reject(message.text)
        if reject:
            message.status = MessageStatus.FILTERED_OUT.value
            message.filter_reason = reject
            message.is_news = False
            message.processed_at = datetime.now(timezone.utc)
            await self._session.flush()
            return ProcessResult(event=None, action="filtered")

        if self._ad_det.looks_like_ad(message.text):
            message.status = MessageStatus.FILTERED_OUT.value
            message.filter_reason = "advertisement"
            message.is_advertisement = True
            message.is_news = False
            message.processed_at = datetime.now(timezone.utc)
            await self._session.flush()
            return ProcessResult(event=None, action="ad")

        # 2) Language + raw embedding (reuse later)
        message.language = await self._ai.detect_language(message.text)
        raw_emb = self._embed_svc.embed(message.text)
        message.raw_embedding = raw_emb

        # 3) Try merge against existing Events BEFORE AI (save cost)
        candidates = await self._load_candidates()
        light_ents = light_entities_from_text(message.text)
        assignment = self._merge.find_match(
            message.text,
            raw_emb,
            candidates,
            entities=light_ents or None,
        )
        if not assignment.is_new and assignment.news_id is not None:
            event = await self._attach(
                event_id=assignment.news_id,
                message=message,
                channel_title=channel_title,
                channel_username=channel_username,
                embedding=raw_emb,
            )
            return ProcessResult(event=event, action="merged")

        # 4) One-shot AI analysis (create path only)
        analysis = await self._ai.analyze_post(
            message.text,
            source_count=1,
            channel_title=channel_title,
        )
        await log_ai_usage(
            self._session,
            provider=getattr(self._ai, "provider_name", "unknown"),
            operation="analyze_post",
        )

        message.raw_entities = list(analysis.entities)
        if analysis.language:
            message.language = analysis.language

        if analysis.is_advertisement or self._ad_det.from_analysis(analysis):
            message.status = MessageStatus.FILTERED_OUT.value
            message.filter_reason = analysis.reason or "advertisement"
            message.is_advertisement = True
            message.is_news = False
            message.processed_at = datetime.now(timezone.utc)
            await self._session.flush()
            return ProcessResult(event=None, action="ad")

        if not analysis.is_news:
            message.status = MessageStatus.FILTERED_OUT.value
            message.filter_reason = analysis.reason or "not_news"
            message.is_news = False
            message.processed_at = datetime.now(timezone.utc)
            await self._session.flush()
            return ProcessResult(event=None, action="filtered")

        message.is_news = True
        message.is_advertisement = False

        entities = list(analysis.entities)
        event_emb = self._merge.embed_event_text(
            title=analysis.title,
            summary=analysis.summary,
            topic=analysis.topic,
            entities=entities,
        )

        # Second-chance merge with richer event embedding
        candidates = await self._load_candidates()
        assignment = self._merge.find_match(
            f"{analysis.title}\n{analysis.summary}",
            event_emb,
            candidates,
            entities=entities,
        )
        if not assignment.is_new and assignment.news_id is not None:
            event = await self._attach(
                event_id=assignment.news_id,
                message=message,
                channel_title=channel_title,
                channel_username=channel_username,
                embedding=event_emb,
            )
            return ProcessResult(event=event, action="merged")

        timeline = [
            make_entry(
                kind="created",
                text="Событие создано",
                sources=1,
            )
        ]
        ref_now = datetime.now(timezone.utc)
        event = Event(
            title=strip_at_mentions(resolve_relative_dates(analysis.title, ref_now)),
            summary=strip_at_mentions(resolve_relative_dates(analysis.summary, ref_now)),
            category=analysis.category,
            topic=strip_at_mentions(resolve_relative_dates(analysis.topic or "", ref_now)) or None,
            why_important=analysis.why_important,
            entities=entities,
            keywords=list(analysis.keywords),
            importance_score=Decimal(str(analysis.importance_score)),
            embedding=list(event_emb),
            status="active",
            timeline=timeline,
            sources_count=1,
            posts_count=1,
            ai_reasoning=analysis.reasoning or analysis.why_important,
        )
        self._session.add(event)
        await self._session.flush()
        self._session.add(
            EventSource(
                event_id=event.id,
                message_id=message.id,
                source_url=message.url,
                channel_title=channel_title,
                channel_username=channel_username,
            )
        )
        message.status = MessageStatus.PROCESSED.value
        message.processed_at = datetime.now(timezone.utc)
        await self._session.flush()
        await self._ingest_knowledge(event)
        return ProcessResult(event=event, action="created")

    async def _attach(
        self,
        *,
        event_id: int,
        message: Message,
        channel_title: str | None,
        channel_username: str | None,
        embedding: list[float],
    ) -> Event:
        event = await self._session.get(
            Event,
            event_id,
            options=(selectinload(Event.sources),),
        )
        assert event is not None

        self._session.add(
            EventSource(
                event_id=event.id,
                message_id=message.id,
                source_url=message.url,
                channel_title=channel_title,
                channel_username=channel_username,
            )
        )
        message.status = MessageStatus.PROCESSED.value
        message.is_news = True
        message.processed_at = datetime.now(timezone.utc)
        event.updated_at = datetime.now(timezone.utc)
        if event.embedding is None:
            event.embedding = list(embedding)

        await self._session.flush()
        await self._session.refresh(event, attribute_names=["sources"])
        prev = event.sources_count or 0
        await self.rescore_event(event.id)
        await self._session.refresh(event, attribute_names=["sources", "importance_score", "sources_count", "posts_count", "timeline"])

        # Union light entities into Event on merge (feeds KG without re-LLM)
        light = light_entities_from_text(message.text)
        if light:
            existing = list(event.entities or [])
            seen = {str(x).lower() for x in existing}
            for e in light:
                if e.lower() not in seen:
                    existing.append(e)
                    seen.add(e.lower())
            event.entities = existing[:40]

        n_sources = event.sources_count or len(event.sources or [])
        event.timeline = self._timeline.append(
            event.timeline,
            make_entry(
                kind="sources",
                text=f"Добавилось подтверждение. Теперь {n_sources} источников.",
                sources=n_sources,
            ),
        )
        # Significant growth → keep AI fields; no re-analyze unless huge delta
        if n_sources - prev >= SIGNIFICANT_SOURCES_DELTA:
            event.timeline = self._timeline.append(
                event.timeline,
                make_entry(
                    kind="growth",
                    text=f"Событие заметно выросло: {n_sources} источников.",
                    sources=n_sources,
                ),
            )
        await self._session.flush()
        await self._ingest_knowledge(event, extra_entities=light or None)
        return event

    async def _ingest_knowledge(self, event: Event, *, extra_entities: list[str] | None = None) -> None:
        try:
            from app.services.knowledge import KnowledgeGraphService

            await KnowledgeGraphService(self._session).ingest_event(
                event, extra_entities=extra_entities
            )
        except Exception:
            logger.exception("Knowledge graph ingest failed for event %s", event.id)

    async def _load_candidates(self) -> list[ClusterCandidate]:
        since = datetime.now(timezone.utc) - timedelta(hours=self._lookback_hours)
        result = await self._session.execute(
            select(Event)
            .where(Event.status == "active")
            .where(Event.updated_at >= since)
            .order_by(Event.updated_at.desc())
            .limit(200)
        )
        events = list(result.scalars().all())
        candidates: list[ClusterCandidate] = []
        for event in events:
            vector = event.embedding
            if not vector:
                vector = self._merge.embed_event_text(
                    title=event.title,
                    summary=event.summary,
                    topic=event.topic,
                    entities=list(event.entities or []),
                )
                event.embedding = list(vector)
            candidates.append(
                ClusterCandidate(
                    news_id=event.id,
                    title=event.title,
                    summary=event.summary,
                    embedding=vector,
                    entities=list(event.entities or []),
                )
            )
        return candidates

    async def rescore_event(self, event_id: int) -> float:
        event = await self._session.get(
            Event,
            event_id,
            options=(selectinload(Event.sources),),
        )
        if not event:
            return 0.0

        texts: list[str] = [event.summary or event.title]
        timestamps: list[float] = []
        for src in event.sources:
            if src.message_id:
                msg = await self._session.get(Message, src.message_id)
                if msg:
                    texts.append(msg.text)
                    timestamps.append(msg.published_at.timestamp())

        base = float(event.importance_score)
        source_boost = min(3.0, max(0, len(event.sources) - 1) * 0.6)
        heuristic = self._scorer.score(
            source_count=len(event.sources),
            text="\n".join(texts),
            published_at_timestamps=timestamps or [time.time()],
            now_timestamp=time.time(),
        )
        score = round(min(10.0, max(base + source_boost, heuristic)), 2)
        event.importance_score = Decimal(str(score))
        event.sources_count = len(event.sources or [])
        event.posts_count = event.sources_count
        if event.sources_count > 1:
            base_why = event.why_important or ""
            marker = f"{event.sources_count} источников"
            if marker not in base_why:
                event.why_important = (
                    f"{base_why}; {marker}".strip("; ")
                    if base_why
                    else f"Подтверждено {event.sources_count} источниками"
                )
        await self._session.flush()
        return score

    # --- query helpers (facade for bot) ---

    async def get_event(self, event_id: int) -> Event | None:
        return await self._session.get(
            Event,
            event_id,
            options=(
                selectinload(Event.sources).selectinload(EventSource.message),
            ),
        )

    async def get_top_events(self, *, limit: int = 5, offset: int = 0) -> list[Event]:
        result = await self._session.execute(
            select(Event)
            .options(selectinload(Event.sources))
            .where(Event.status == "active")
            .order_by(Event.importance_score.desc(), Event.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def semantic_candidates(
        self,
        query: str,
        *,
        limit: int = 20,
        since: datetime | None = None,
    ) -> list[tuple[Event, float]]:
        cutoff = since or (datetime.now(timezone.utc) - timedelta(days=30))
        result = await self._session.execute(
            select(Event)
            .options(selectinload(Event.sources))
            .where(Event.status == "active")
            .where(Event.created_at >= cutoff)
            .order_by(Event.created_at.desc())
            .limit(500)
        )
        events = list(result.scalars().all())
        q_vec = self._embedding.embed_one(query)
        scored: list[tuple[Event, float]] = []
        for event in events:
            vec = event.embedding
            if not vec:
                continue
            scored.append((event, cosine_similarity(q_vec, vec)))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:limit]


# Compat facade
class NewsService(EventPipeline):
    async def process_message(self, message: Message, *, channel_title: str | None = None, channel_username: str | None = None):
        return await self.process_post(
            message, channel_title=channel_title, channel_username=channel_username
        )

    async def get_news(self, news_id: int):
        return await self.get_event(news_id)

    async def get_top_news(self, *, limit: int = 5, offset: int = 0):
        return await self.get_top_events(limit=limit, offset=offset)

    async def get_daily_news(self, *, limit: int = 10):
        since = datetime.now(timezone.utc) - timedelta(hours=24)
        result = await self._session.execute(
            select(Event)
            .options(selectinload(Event.sources))
            .where(Event.status == "active")
            .where(Event.created_at >= since)
            .order_by(Event.importance_score.desc(), Event.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def rescore_news(self, news_id: int) -> float:
        return await self.rescore_event(news_id)

    async def count_sources(self, news_id: int) -> int:
        result = await self._session.execute(
            select(func.count()).select_from(EventSource).where(EventSource.event_id == news_id)
        )
        return int(result.scalar_one())
