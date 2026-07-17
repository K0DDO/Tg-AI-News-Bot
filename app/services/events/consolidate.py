"""Offline Event consolidation — merge near-duplicate Events into one story."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.models import Event, EventSource
from app.services.embedding import EmbeddingService
from app.services.events.merge import EventMergeService, is_near_duplicate
from app.services.events.timeline import make_entry
from app.services.ports import ClusterCandidate, ClusterResult

logger = logging.getLogger(__name__)

ProgressCb = Callable[[dict], None]


class EventConsolidateService:
    """
    Rematch existing active Events and fold duplicates into winners.
    Winner keeps title/summary; sources move from losers; losers → status=merged.
    """

    def __init__(self, session: AsyncSession) -> None:
        settings = get_settings()
        self._session = session
        self._embed = EmbeddingService()
        self._merge = EventMergeService(
            self._embed.port,
            threshold=settings.cluster_similarity_threshold,
            time_window_hours=settings.event_merge_time_window_hours,
        )
        self._threshold = float(settings.cluster_similarity_threshold)
        if "hash" in str(getattr(self._embed.port, "backend", "")).lower():
            self._threshold = min(self._threshold, 0.52)

    async def consolidate_all(
        self,
        *,
        batch_commit_every: int = 40,
        on_progress: ProgressCb | None = None,
        should_stop: Callable[[], bool] | None = None,
    ) -> dict[str, int]:
        result = await self._session.execute(
            select(Event)
            .where(Event.status == "active")
            .order_by(Event.sources_count.desc(), Event.importance_score.desc(), Event.id.asc())
            .options(selectinload(Event.sources))
        )
        events = list(result.scalars().unique().all())
        total = len(events)
        winners: list[Event] = []
        winner_cands: list[ClusterCandidate] = []
        merged = 0
        duplicates = 0
        processed = 0

        def _report(**extra: int | str) -> None:
            if on_progress:
                on_progress(
                    {
                        "phase": "consolidate",
                        "processed": processed,
                        "total": total,
                        "merged": merged,
                        "duplicates_found": duplicates,
                        "unique_events": len(winners),
                        **extra,
                    }
                )

        for event in events:
            if should_stop and should_stop():
                break
            processed += 1
            text = f"{event.title or ''}\n{event.summary or ''}"
            vector = list(event.embedding) if event.embedding else None
            if not vector:
                vector = self._merge.embed_event_text(
                    title=event.title or "",
                    summary=event.summary or "",
                    topic=event.topic,
                    entities=list(event.entities or []),
                )
                event.embedding = list(vector)

            match = self._merge.find_match(
                text,
                vector,
                winner_cands,
                entities=list(event.entities or []) or None,
                keywords=list(event.keywords or []) or None,
                category=event.category,
                created_at=event.created_at,
            )
            near_any = False
            if match.is_new or match.news_id is None:
                # Extra lexical pass against recent winners
                for cand in winner_cands[-80:]:
                    if is_near_duplicate(text, f"{cand.title}\n{cand.summary}"):
                        near_any = True
                        match = ClusterResult(
                            news_id=cand.news_id,
                            similarity=max(match.similarity, self._threshold),
                            is_new=False,
                        )
                        break

            if (not match.is_new and match.news_id is not None) or near_any:
                winner = next((w for w in winners if w.id == match.news_id), None)
                if winner is None:
                    winners.append(event)
                    winner_cands.append(self._to_candidate(event, vector))
                else:
                    moved = await self._fold_into(winner, event)
                    merged += 1
                    duplicates += 1
                    if moved:
                        # refresh winner candidate sources/embedding in list
                        for i, c in enumerate(winner_cands):
                            if c.news_id == winner.id:
                                winner_cands[i] = self._to_candidate(winner, list(winner.embedding or vector))
                                break
            else:
                winners.append(event)
                winner_cands.append(self._to_candidate(event, vector))

            if processed % 10 == 0:
                _report()
            if processed % batch_commit_every == 0:
                await self._session.commit()

        await self._session.commit()
        _report(phase="consolidate_done")
        return {
            "processed": processed,
            "total": total,
            "merged": merged,
            "duplicates_found": duplicates,
            "unique_events": len(winners),
        }

    def _to_candidate(self, event: Event, vector: list[float]) -> ClusterCandidate:
        return ClusterCandidate(
            news_id=event.id,
            title=event.title or "",
            summary=event.summary or "",
            embedding=vector,
            entities=list(event.entities or []),
            keywords=list(event.keywords or []),
            category=event.category,
            created_at=event.created_at,
        )

    async def _fold_into(self, winner: Event, loser: Event) -> int:
        """Move sources from loser → winner; mark loser merged."""
        if winner.id == loser.id:
            return 0
        await self._session.refresh(loser, attribute_names=["sources"])
        await self._session.refresh(winner, attribute_names=["sources"])
        moved = 0
        existing_urls = {s.source_url for s in (winner.sources or []) if s.source_url}
        existing_msgs = {s.message_id for s in (winner.sources or []) if s.message_id}

        for src in list(loser.sources or []):
            if src.message_id and src.message_id in existing_msgs:
                await self._session.delete(src)
                continue
            if src.source_url and src.source_url in existing_urls:
                await self._session.delete(src)
                continue
            src.event_id = winner.id
            moved += 1
            if src.source_url:
                existing_urls.add(src.source_url)
            if src.message_id:
                existing_msgs.add(src.message_id)

        # Union entities / keywords
        w_ents = list(winner.entities or [])
        seen = {str(x).lower() for x in w_ents}
        for e in loser.entities or []:
            if str(e).lower() not in seen:
                w_ents.append(e)
                seen.add(str(e).lower())
        winner.entities = w_ents[:40]

        w_kw = list(winner.keywords or [])
        seen_kw = {str(x).lower() for x in w_kw}
        for k in loser.keywords or []:
            if str(k).lower() not in seen_kw:
                w_kw.append(k)
                seen_kw.add(str(k).lower())
        winner.keywords = w_kw[:40]

        # Prefer higher importance; keep better title if loser has more sources historically
        if float(loser.importance_score or 0) > float(winner.importance_score or 0):
            winner.importance_score = loser.importance_score
        if (loser.sources_count or 0) > (winner.sources_count or 0) and loser.title:
            # Keep winner title usually; only swap if winner was thin
            if (winner.sources_count or 0) <= 1 and len(loser.title or "") > 8:
                winner.title = loser.title
                if loser.summary:
                    winner.summary = loser.summary

        await self._session.flush()
        await self._session.refresh(winner, attribute_names=["sources"])
        n = len(winner.sources or [])
        winner.sources_count = n
        winner.posts_count = n
        winner.updated_at = datetime.now(timezone.utc)
        winner.timeline = list(winner.timeline or []) + [
            make_entry(
                kind="merged",
                text=f"Объединено с событием #{loser.id}. Источников: {n}.",
                sources=n,
            )
        ]

        loser.status = "merged"
        loser.related_event_ids = [winner.id]
        loser.sources_count = 0
        loser.posts_count = 0
        loser.updated_at = datetime.now(timezone.utc)
        await self._session.flush()
        return moved
