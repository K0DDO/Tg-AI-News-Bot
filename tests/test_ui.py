"""UI formatter and channel import parse tests."""

from decimal import Decimal

from app.bot.ui.texts import circled, format_feed, format_home
from app.models.news import News
from app.services.channels.import_parse import parse_channel_refs
from app.services.search.semantic import parse_period_days, significant_tokens


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
    news = News(
        id=1,
        title="Test",
        summary="Long summary should not appear in feed",
        category="AI",
        importance_score=Decimal("8.1"),
        sources_count=0,
    )
    news.sources = []
    feed = format_feed("ru", [news])
    assert "①" in feed or "1" in feed
    assert "Long summary" not in feed
    assert circled(1) == "①"


def test_period_and_tokens():
    assert parse_period_days("новости NVIDIA за неделю") == 7
    assert parse_period_days("today about Apple") == 1
    assert "nvidia" in significant_tokens("what about NVIDIA chips")
