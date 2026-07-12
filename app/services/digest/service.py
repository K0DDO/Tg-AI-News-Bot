"""News clustering + AI analysis with cost-aware pipeline."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from dataclasses import dataclass

from app.models import Message, MessageStatus, News, NewsSource
from app.services.ai import AIService, create_ai_service
from app.services.ai.usage import log_ai_usage
from app.services.clustering import CosineClusterer, HashingEmbedding, cosine_similarity
from app.services.filter import RuleBasedFilter
from app.services.ports import ClusterCandidate, EmbeddingPort, FilterPort, ScorerPort
from app.services.scoring import ImportanceScorer

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ProcessResult:
    news: News | None
    action: str  # filtered | merged | created


class NewsService:
    """
    Optimized pipeline:

    raw message
      → rule filter (no AI)
      → embedding + cosine merge (no AI)
      → if duplicate: attach NewsSource, bump score (no AI)
      → if new: AIService.analyze_message (Groq/heuristic)
    """

    def __init__(
        self,
        session: AsyncSession,
        *,
        filter_port: FilterPort | None = None,
        embedding: EmbeddingPort | None = None,
        clusterer: CosineClusterer | None = None,
        ai: AIService | None = None,
        scorer: ScorerPort | None = None,
    ) -> None:
        settings = get_settings()
        self._session = session
        self._filter = filter_port or RuleBasedFilter()
        self._embedding = embedding or HashingEmbedding()
        self._clusterer = clusterer or CosineClusterer()
        self._ai = ai or create_ai_service()
        self._scorer = scorer or ImportanceScorer()
        self._threshold = settings.cluster_similarity_threshold
        self._lookback_hours = settings.cluster_lookback_hours

    async def process_message(
        self,
        message: Message,
        *,
        channel_title: str | None = None,
        channel_username: str | None = None,
    ) -> ProcessResult:
        result = self._filter.evaluate(message.text)
        if not result.passed:
            message.status = MessageStatus.FILTERED_OUT.value
            message.filter_reason = result.reason
            await self._session.flush()
            return ProcessResult(news=None, action="filtered")

        embedding = self._embedding.embed_one(message.text)
        candidates = await self._load_candidates()
        assignment = self._clusterer.assign(
            message.text,
            embedding,
            candidates,
            self._threshold,
        )

        if not assignment.is_new and assignment.news_id is not None:
            news = await self._attach_to_existing(
                news_id=assignment.news_id,
                message=message,
                channel_title=channel_title,
                channel_username=channel_username,
                embedding=embedding,
            )
            return ProcessResult(news=news, action="merged")

        analysis = await self._ai.analyze_message(
            message.text,
            source_count=1,
            channel_title=channel_title,
        )
        await log_ai_usage(
            self._session,
            provider=getattr(self._ai, "provider_name", "unknown"),
            operation="analyze_message",
        )

        if not analysis.is_news:
            message.status = MessageStatus.FILTERED_OUT.value
            message.filter_reason = analysis.reason or "ai_not_news"
            await self._session.flush()
            return ProcessResult(news=None, action="filtered")

        news = News(
            title=analysis.title,
            summary=analysis.summary,
            category=analysis.category,
            topic=analysis.topic,
            why_important=analysis.why_important,
            importance_score=Decimal(str(analysis.importance_score)),
            sources_count=1,
            embedding=list(embedding),
        )
        self._session.add(news)
        await self._session.flush()

        self._session.add(
            NewsSource(
                news_id=news.id,
                message_id=message.id,
                source_url=message.url,
                channel_title=channel_title,
                channel_username=channel_username,
            )
        )
        message.status = MessageStatus.PROCESSED.value
        await self._session.flush()
        return ProcessResult(news=news, action="created")

    async def _attach_to_existing(
        self,
        *,
        news_id: int,
        message: Message,
        channel_title: str | None,
        channel_username: str | None,
        embedding: list[float],
    ) -> News:
        news = await self._session.get(
            News,
            news_id,
            options=(selectinload(News.sources),),
        )
        assert news is not None

        self._session.add(
            NewsSource(
                news_id=news.id,
                message_id=message.id,
                source_url=message.url,
                channel_title=channel_title,
                channel_username=channel_username,
            )
        )
        message.status = MessageStatus.PROCESSED.value
        news.updated_at = datetime.now(timezone.utc)
        if news.embedding is None:
            news.embedding = list(embedding)

        await self._session.flush()
        await self.rescore_news(news.id)
        await self._session.refresh(news, attribute_names=["sources", "importance_score", "sources_count"])
        return news

    async def _load_candidates(self) -> list[ClusterCandidate]:
        since = datetime.now(timezone.utc) - timedelta(hours=self._lookback_hours)
        result = await self._session.execute(
            select(News).where(News.updated_at >= since).order_by(News.updated_at.desc()).limit(200)
        )
        news_items = list(result.scalars().all())
        candidates: list[ClusterCandidate] = []
        for news in news_items:
            vector = news.embedding
            if not vector:
                vector = self._embedding.embed_one(f"{news.title}\n{news.summary}")
                news.embedding = list(vector)
            candidates.append(
                ClusterCandidate(
                    news_id=news.id,
                    title=news.title,
                    summary=news.summary,
                    embedding=vector,
                )
            )
        return candidates

    async def rescore_news(self, news_id: int) -> float:
        news = await self._session.get(
            News,
            news_id,
            options=(selectinload(News.sources),),
        )
        if not news:
            return 0.0

        texts: list[str] = [news.summary or news.title]
        timestamps: list[float] = []
        for src in news.sources:
            if src.message_id:
                msg = await self._session.get(Message, src.message_id)
                if msg:
                    texts.append(msg.text)
                    timestamps.append(msg.published_at.timestamp())

        # Keep AI base score, boost by extra sources (no new Groq call)
        base = float(news.importance_score)
        source_boost = min(3.0, max(0, len(news.sources) - 1) * 0.6)
        heuristic = self._scorer.score(
            source_count=len(news.sources),
            text="\n".join(texts),
            published_at_timestamps=timestamps or [time.time()],
            now_timestamp=time.time(),
        )
        score = round(min(10.0, max(base, heuristic) + source_boost * 0.15), 2)
        # Prefer max of AI score and heuristic, plus mild source boost on AI score
        score = round(min(10.0, max(base + source_boost, heuristic)), 2)
        news.importance_score = Decimal(str(score))
        news.sources_count = len(news.sources or [])
        # Refresh why_important lightly without extra AI call
        if news.sources_count > 1:
            base_why = news.why_important or ""
            marker = f"{news.sources_count} источников"
            if marker not in base_why:
                news.why_important = (
                    f"{base_why}; {marker}".strip("; ")
                    if base_why
                    else f"Подтверждено {news.sources_count} источниками"
                )
        await self._session.flush()
        return score

    async def get_top_news(self, *, limit: int = 5, offset: int = 0) -> list[News]:
        result = await self._session.execute(
            select(News)
            .options(selectinload(News.sources))
            .order_by(News.importance_score.desc(), News.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_daily_news(self, *, limit: int = 10) -> list[News]:
        since = datetime.now(timezone.utc) - timedelta(hours=24)
        result = await self._session.execute(
            select(News)
            .options(selectinload(News.sources))
            .where(News.created_at >= since)
            .order_by(News.importance_score.desc(), News.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_news(self, news_id: int) -> News | None:
        return await self._session.get(
            News,
            news_id,
            options=(selectinload(News.sources),),
        )

    async def count_sources(self, news_id: int) -> int:
        result = await self._session.execute(
            select(func.count()).select_from(NewsSource).where(NewsSource.news_id == news_id)
        )
        return int(result.scalar_one())

    async def semantic_candidates(
        self,
        query: str,
        *,
        limit: int = 8,
        lookback_days: int = 30,
        since: datetime | None = None,
    ) -> list[tuple[News, float]]:
        query_vec = self._embedding.embed_one(query)
        cutoff = since or (datetime.now(timezone.utc) - timedelta(days=lookback_days))
        result = await self._session.execute(
            select(News)
            .options(selectinload(News.sources))
            .where(News.created_at >= cutoff)
            .order_by(News.created_at.desc())
            .limit(500)
        )
        scored: list[tuple[News, float]] = []
        for news in result.scalars().all():
            vector = news.embedding
            if not vector:
                vector = self._embedding.embed_one(f"{news.title}\n{news.summary}")
            sim = cosine_similarity(query_vec, vector)
            scored.append((news, sim))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:limit]
