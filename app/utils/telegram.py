"""Build a public t.me link to an original channel post."""


def build_message_url(*, username: str | None, channel_id: int, message_id: int) -> str:
    if username:
        return f"https://t.me/{username.lstrip('@')}/{message_id}"
    # Private / numeric channel: -100XXXXXXXXXX → c/XXXXXXXXXX
    raw = abs(channel_id)
    if str(raw).startswith("100"):
        raw = int(str(raw)[3:])
    return f"https://t.me/c/{raw}/{message_id}"
