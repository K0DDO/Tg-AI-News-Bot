"""UI formatter and search helpers."""

from datetime import date
from decimal import Decimal

from app.bot.ui.texts import circled, format_feed, format_home, format_meta_line
from app.models.event import Event
from app.models.user_prefs import UserEventState
from app.services.channels.import_parse import parse_channel_refs
from app.services.preferences import FeedService
from app.services.search.semantic import extract_query_entities, parse_period_days, significant_tokens
from app.utils.relative_dates import resolve_relative_dates
from app.utils.title_case import normalize_title


def test_parse_channel_refs_mixed():
    text = """
    @OpenAI
    https://t.me/nvidia
    t.me/s/techcrunch
    https://telegram.me/reuters
    telegram.me/s/bbcworld
    junk
    """
    assert parse_channel_refs(text) == [
        "openai",
        "nvidia",
        "techcrunch",
        "reuters",
        "bbcworld",
    ]


def test_format_home_and_feed():
    text = format_home("ru", read=10, saved=3, liked=2, last_update=None)
    assert "Briefly" in text
    assert "10" in text
    event = Event(
        id=1,
        title="Test",
        summary="Long summary should not appear in feed",
        category="ai_software",
        importance_score=Decimal("8.1"),
        sources_count=2,
        posts_count=3,
        status="active",
    )
    event.sources = []
    feed = format_feed("ru", [event])
    assert "①" in feed or "1" in feed
    assert "Long summary" not in feed
    assert "⭐️ 8.1/10 • 📂 🤖 AI &amp; Software • 📡 2 • 📰 3" in feed
    assert circled(1) == "①"


def test_meta_line():
    assert format_meta_line(score=8.0, category="technology", sources=1, posts=1) == (
        "⭐️ 8.0/10 • 📂 💻 Technology • 📡 1 • 📰 1"
    )


def test_normalize_title_caps():
    assert normalize_title("STEAM MACHINE лучше PS5 И Xbox") == "Steam Machine Лучше PS5 И Xbox"
    assert normalize_title("Normal title already") == "Normal title already"


def test_resolve_relative_dates():
    d = date(2026, 7, 13)
    assert resolve_relative_dates("завтра Apple представит iPhone", d) == "14.07 Apple представит iPhone"
    assert "13.07" in resolve_relative_dates("сегодня релиз", d)
    assert "15.07" in resolve_relative_dates("послезавтра релиз", d)
    assert "16.07" in resolve_relative_dates("через 3 дня анонс", d)


def test_should_show_strict_unread():
    assert FeedService._should_show(None) is True
    unread = UserEventState(user_id=1, event_id=1, is_read=False)
    assert FeedService._should_show(unread) is True
    read = UserEventState(user_id=1, event_id=1, is_read=True, score_at_interaction=Decimal("5"))
    assert FeedService._should_show(read) is False
    hidden = UserEventState(user_id=1, event_id=1, is_read=False, is_hidden=True)
    assert FeedService._should_show(hidden) is False


def test_period_and_tokens():
    assert parse_period_days("новости NVIDIA за неделю") == 7
    assert parse_period_days("today about Apple") == 1
    assert "nvidia" in significant_tokens("what about NVIDIA chips")
    ents = extract_query_entities("Что нового по iPhone 18 Pro?")
    assert any("iphone" in e.lower() for e in ents)
