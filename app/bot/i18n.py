"""i18n for Briefly UI — loads translations from locales/*.json."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SUPPORTED_LANGS = ("ru", "en", "de", "es", "zh")

LANG_LABELS = {
    "ru": "Русский",
    "en": "English",
    "de": "Deutsch",
    "es": "Español",
    "zh": "中文",
}

_LOCALES_DIR = Path(__file__).resolve().parents[2] / "locales"
_STRINGS: dict[str, dict[str, str]] = {}


def _load_locales() -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for code in SUPPORTED_LANGS:
        path = _LOCALES_DIR / f"{code}.json"
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(data, dict):
            out[code] = {str(k): str(v) for k, v in data.items()}
    return out


_STRINGS = _load_locales()


def reload_locales() -> None:
    """Reload JSON locales (tests / hot-reload)."""
    global _STRINGS
    _STRINGS = _load_locales()


def t(lang: str, key: str, **kwargs: Any) -> str:
    lang = lang if lang in _STRINGS else "ru"
    text = _STRINGS.get(lang, {}).get(key)
    if text is None:
        text = _STRINGS.get("en", {}).get(key) or _STRINGS.get("ru", {}).get(key) or key
    if kwargs:
        try:
            return text.format(**kwargs)
        except Exception:
            return text
    return text


def btn_feed(lang: str) -> str:
    return f"📰 {t(lang, 'feed')}"


def btn_search(lang: str) -> str:
    return f"🔍 {t(lang, 'search')}"


def btn_channels(lang: str) -> str:
    return f"📡 {t(lang, 'channels')}"


def btn_settings(lang: str) -> str:
    return f"⚙️ {t(lang, 'settings')}"


def btn_trends(lang: str) -> str:
    return f"🔥 {t(lang, 'trends')}"


def btn_favorites(lang: str) -> str:
    return f"⭐ {t(lang, 'favorites')}"


def btn_history(lang: str) -> str:
    return f"📚 {t(lang, 'history')}"
