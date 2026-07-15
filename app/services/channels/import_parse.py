"""Parse bulk channel usernames / t.me + telegram.me links from user input."""

from __future__ import annotations

import re

# t.me and telegram.me (both public link forms); optional /s/ preview prefix
_USER = re.compile(
    r"(?:https?://)?(?:www\.)?(?:t\.me|telegram\.me)/(?:s/)?([A-Za-z0-9_]{4,})"
    r"|@([A-Za-z0-9_]{4,})",
    re.I,
)
_BLOCKED = {"joinchat", "addstickers", "share", "proxy", "socks", "iv"}


def parse_channel_refs(text: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        for m in _USER.finditer(line):
            username = (m.group(1) or m.group(2) or "").lower()
            if not username or username in _BLOCKED:
                continue
            if username not in seen:
                seen.add(username)
                found.append(username)
    return found
