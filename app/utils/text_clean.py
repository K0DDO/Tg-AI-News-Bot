"""Clean Telegram-specific noise from event titles/summaries."""

from __future__ import annotations

import re

# @username mentions
_AT_USER = re.compile(r"(?i)(?<!\w)@[\w\d_]{2,64}\b")
# «эксклюзив @channel», «передаёт @x», «источники @y»
_ATTRIB = re.compile(
    r"(?i)[,;:\-—–]?\s*(?:эксклюзив|источник(?:и)?|переда[юя]т\s+источники|"
    r"via|source(?:s)?)\s*@[\w\d_]{2,64}\b"
)
_MULTI_SPACE = re.compile(r"[ \t]{2,}")
_TRAIL_PUNCT = re.compile(r"[\s,;:\-—–]+$")


def strip_at_mentions(text: str | None) -> str:
    """Remove @channel / @user mentions and attribution fluff from news text."""
    if not text:
        return ""
    s = _ATTRIB.sub("", text)
    s = _AT_USER.sub("", s)
    s = _MULTI_SPACE.sub(" ", s)
    s = _TRAIL_PUNCT.sub("", s.strip())
    # tidy leftover empty parentheses / dashes
    s = re.sub(r"\(\s*\)", "", s)
    s = re.sub(r"\s{2,}", " ", s).strip()
    return s
