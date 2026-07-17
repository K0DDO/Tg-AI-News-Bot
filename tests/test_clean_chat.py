"""Clean-chat middleware must only target user reply-button presses."""

from types import SimpleNamespace

from app.bot.middlewares.clean_chat import _is_user_reply_button, _reply_action_texts


def _msg(*, text: str, is_bot: bool = False, reply_markup=None):
    return SimpleNamespace(
        text=text,
        from_user=SimpleNamespace(is_bot=is_bot, id=1),
        reply_markup=reply_markup,
    )


def test_user_reply_buttons_are_detected():
    texts = _reply_action_texts()
    assert "📰 Лента" in texts or any("Лента" in t or "Feed" in t for t in texts)
    sample = next(iter(texts))
    assert _is_user_reply_button(_msg(text=sample)) is True


def test_bot_messages_never_match():
    sample = next(iter(_reply_action_texts()))
    assert _is_user_reply_button(_msg(text=sample, is_bot=True)) is False


def test_free_text_not_deleted():
    assert _is_user_reply_button(_msg(text="привет, найди новости про OpenAI")) is False
    assert _is_user_reply_button(_msg(text="/start")) is False


def test_message_with_inline_keyboard_not_treated_as_user_button():
    sample = next(iter(_reply_action_texts()))
    assert _is_user_reply_button(_msg(text=sample, reply_markup=object())) is False
