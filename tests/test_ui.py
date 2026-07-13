"""UI formatter and search helpers."""

from decimal import Decimal

from app.bot.ui.texts import circled, format_feed, format_home
from app.models.event import Event
from app.services.channels.import_parse import parse_channel_refs
from app.services.search.semantic import extract_query_entities, parse_period_days, significant_tokens


def test_parse_channel_refs_mixed():
    text = """
    @OpenAI
    https://t.me/nvidia
    t.me/s/techcrunch
    junk
    """
    assert parse_channel_refs(text) == ["openai", "nvidia", "techcrunch"]


def test_format_home_and_feed():
    text = format_home("ru", messages=10, news=3, avg_importance=7.2, last_update=None)
    assert "Briefly" in text
    assert "10" in text
    event = Event(
        id=1,
        title="Test",
        summary="Long summary should not appear in feed",
        category="AI",
        importance_score=Decimal("8.1"),
        sources_count=0,
        posts_count=0,
        status="active",
    )
    event.sources = []
    feed = format_feed("ru", [event])
    assert "①" in feed or "1" in feed
    assert "Long summary" not in feed
    assert circled(1) == "①"


def test_resolve_relative_dates():
    from datetime import date

    from app.utils.relative_dates import resolve_relative_dates

    d = date(2026, 7, 13)
    assert resolve_relative_dates("завтра Apple представит iPhone", d) == "14.07 Apple представит iPhone"
    assert "13.07" in resolve_relative_dates("сегодня релиз", d)
    assert "15.07" in resolve_relative_dates("послезавтра релиз", d)
    assert "16.07" in resolve_relative_dates("через 3 дня анонс", d)
