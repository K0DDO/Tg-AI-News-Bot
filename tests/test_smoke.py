from app.utils.telegram import build_message_url


def test_build_message_url_with_username():
    assert build_message_url(username="technews", channel_id=-100123, message_id=42) == (
        "https://t.me/technews/42"
    )


def test_build_message_url_without_username():
    url = build_message_url(username=None, channel_id=-1001234567890, message_id=7)
    assert url == "https://t.me/c/1234567890/7"


def test_models_import():
    from app.models import Channel, Event, EventSource, Message, Reaction, TelegramPost, User, UserChannel

    assert User.__tablename__ == "users"
    assert Channel.__tablename__ == "channels"
    assert UserChannel.__tablename__ == "user_channels"
    assert Message.__tablename__ == "messages"
    assert TelegramPost is Message
    assert Event.__tablename__ == "events"
    assert EventSource.__tablename__ == "event_sources"
    assert Reaction.__tablename__ == "reactions"
