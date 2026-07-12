"""Trend topics from clustered news (unique sources + mentions)."""

from __future__ import annotations

import re
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import News

_TOKEN = re.compile(r"[A-Za-zА-Яа-яёЁ0-9][A-Za-zА-Яа-яёЁ0-9\-+]{2,}")
_STOP = {
    "это", "что", "как", "для", "или", "при", "был", "была", "были", "есть",
    "the", "and", "for", "with", "new", "news", "сегодня", "также", "после",
}


class TrendsService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def top_topics(self, *, limit: int = 10) -> list[tuple[str, int]]:
        result = await self._session.execute(
            select(News).options(selectinload(News.sources)).order_by(News.updated_at.desc()).limit(300)
        )
        scores: dict[str, set[int]] = defaultdict(set)
        for news in result.scalars().all():
            text = f"{news.title} {news.summary}"
            tokens = {t.lower() for t in _TOKEN.findall(text) if t.lower() not in _STOP}
            # Prefer capitalized / brand-like tokens from title
            title_tokens = [t for t in _TOKEN.findall(news.title) if t.lower() not in _STOP]
            focus = title_tokens[:4] or list(tokens)[:4]
            for token in focus:
                key = token if token.isupper() or token[:1].isupper() else token.lower()
                if len(key) < 3:
                    continue
                for src in news.sources or []:
                    scores[key].add(src.id)
                if not news.sources:
                    scores[key].add(news.id)
        ranked = sorted(((k, len(v)) for k, v in scores.items()), key=lambda x: x[1], reverse=True)
        return ranked[:limit]
