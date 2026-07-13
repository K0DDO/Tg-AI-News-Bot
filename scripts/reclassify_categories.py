"""Reclassify ALL active events with the current category heuristics."""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import func, select

from app.database import get_session_factory
from app.models import Event
from app.services.categories import classify_event_text


async def main() -> None:
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    sf = get_session_factory()
    moved: dict[str, int] = {}
    samples: list[str] = []

    async with sf() as session:
        result = await session.execute(select(Event).where(Event.status == "active"))
        events = list(result.scalars().all())
        for event in events:
            old = event.category or "Other"
            new = classify_event_text(
                event.title or "",
                event.summary or "",
                event.topic or "",
                current=old,
            )
            if new == old:
                continue
            event.category = new
            key = f"{old}->{new}"
            moved[key] = moved.get(key, 0) + 1
            if len(samples) < 12:
                samples.append(f"  [{old}→{new}] {(event.title or '')[:70]}")
        await session.commit()

        rows = (
            await session.execute(
                select(Event.category, func.count())
                .where(Event.status == "active")
                .group_by(Event.category)
                .order_by(func.count().desc())
            )
        ).all()

    print("samples:")
    for line in samples:
        print(line)
    print("\nreclassified:")
    for k, v in sorted(moved.items(), key=lambda x: -x[1])[:25]:
        print(f"  {k}: {v}")
    print(f"total changes: {sum(moved.values())}")
    print("\ncurrent distribution:")
    for cat, n in rows:
        print(f"  {cat}: {n}")


if __name__ == "__main__":
    asyncio.run(main())
