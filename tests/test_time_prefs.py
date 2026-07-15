"""DND / digest due helpers."""

from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from app.services.time_prefs import is_dnd_active, is_digest_due, trends_window_start


def _settings(**kwargs):
    base = dict(
        timezone="Europe/Moscow",
        dnd_enabled=True,
        dnd_weekday_start="23:00",
        dnd_weekday_end="08:00",
        dnd_weekend_start="00:00",
        dnd_weekend_end="10:00",
        digest_mode="1h",
        digest_time="09:00",
        notifications_enabled=True,
        last_digest_sent_at=None,
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_trends_window_before_8_is_24h():
    # Force by mocking now_local indirectly via timezone - just smoke
    s = _settings()
    start = trends_window_start(s)
    assert start.tzinfo is not None


def test_digest_off_not_due():
    s = _settings(digest_mode="off")
    assert is_digest_due(s) is False


def test_digest_hourly_first_time():
    s = _settings(digest_mode="1h", last_digest_sent_at=None, dnd_enabled=False)
    assert is_digest_due(s) is True
