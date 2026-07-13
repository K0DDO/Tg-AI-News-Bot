"""Feed formatting must not trigger async lazy-loads (MissingGreenlet)."""

from datetime import datetime, timezone
from decimal import Decimal

from app.bot.ui.texts import format_feed
from app.models.event import Event, EventSource
from app.services.events.brief import BriefBuilderService


def _sample_event() -> Event:
    event = Event(
        id=42,
        title="NVIDIA представила новый GPU",
        summary="Кратко о релизе.",
        category="Hardware",
        topic="NVIDIA представила новый GPU для ИИ",
        importance_score=Decimal("8.5"),
        sources_count=2,
        posts_count=2,
        status="active",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        entities=["NVIDIA"],
        timeline=[],
    )
    event.sources = [
        EventSource(
            id=1,
            event_id=42,
            source_url="https://t.me/tech/1",
            channel_title="Tech",
            channel_username="tech",
            created_at=datetime.now(timezone.utc),
        ),
        EventSource(
            id=2,
            event_id=42,
            source_url="https://t.me/ai/2",
            channel_title="AI News",
            channel_username="ainews",
            created_at=datetime.now(timezone.utc),
        ),
    ]
    return event


def test_brief_build_without_message_relationship():
    brief = BriefBuilderService().build(_sample_event(), lang="ru")
    assert brief.event_id == 42
    assert brief.sources_count == 2
    assert brief.sources[0].url.startswith("https://")
    assert brief.sources[0].published_at is not None


def test_format_feed_does_not_need_message():
    text = format_feed("ru", [_sample_event()])
    assert "NVIDIA" in text
    assert "8.5" in text
    assert "Long summary" not in text
