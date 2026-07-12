"""UI formatter and channel import parse tests."""

from app.bot.ui.texts import circled, format_feed, format_home
from app.models.news import News
from app.services.channels.import_parse import parse_channel_refs
from decimal import Decimal


def test_parse_channel_refs_mixed():
    text = """
    @OpenAI
    https://t.me/nvidia
    t.me/s/techcrunch
    junk
    """
    assert parse_channel_refs(text) == ["openai", "nvidia", "techcrunch"]


def test_format_home_and_feed():
    text = format_home(messages=10, news=3, avg_importance=7.2, last_update=None)
    assert "AI News Assistant" in text
    assert "10" in text
    news = News(
        id=1,
        title="Test",
        summary="Long summary should not appear in feed",
        category="AI",
        importance_score=Decimal("8.1"),
    )
    news.sources = []
    feed = format_feed([news])
    assert "①" in feed or "1" in feed
    assert "Long summary" not in feed
    assert circled(1) == "①"
