"""Normalize news titles: avoid ALL CAPS, keep known brand casing."""

from __future__ import annotations

import re

_BRANDS = {
    "ps5": "PS5",
    "ps4": "PS4",
    "xbox": "Xbox",
    "iphone": "iPhone",
    "ipad": "iPad",
    "ios": "iOS",
    "macos": "macOS",
    "gpt": "GPT",
    "chatgpt": "ChatGPT",
    "openai": "OpenAI",
    "nvidia": "NVIDIA",
    "amd": "AMD",
    "ai": "AI",
    "api": "API",
    "cpu": "CPU",
    "gpu": "GPU",
    "usb": "USB",
    "vr": "VR",
    "ar": "AR",
    "llm": "LLM",
    "steam": "Steam",
    "youtube": "YouTube",
    "github": "GitHub",
    "linkedin": "LinkedIn",
    "tiktok": "TikTok",
    "whatsapp": "WhatsApp",
}

_WORD = re.compile(r"[A-Za-zА-Яа-яЁё0-9][\w\-]*", re.UNICODE)


def normalize_title(text: str) -> str:
    """Title-case-ish when the string is mostly uppercase; otherwise leave as-is."""
    raw = (text or "").strip()
    if not raw:
        return raw
    letters = [c for c in raw if c.isalpha()]
    if not letters:
        return raw
    upper_ratio = sum(1 for c in letters if c.isupper()) / len(letters)
    # Only rewrite when mostly CAPS
    if upper_ratio < 0.65:
        return raw

    def repl(m: re.Match[str]) -> str:
        word = m.group(0)
        key = word.lower()
        if key in _BRANDS:
            return _BRANDS[key]
        if word.isdigit():
            return word
        # Keep short all-caps acronyms (2–4) if known or all letters
        if len(word) <= 3 and word.isalpha() and key.upper() == word.upper():
            return word.upper() if key in _BRANDS or len(word) <= 2 else word.capitalize()
        return word.capitalize()

    return _WORD.sub(repl, raw.lower())
