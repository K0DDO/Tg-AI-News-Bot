"""Fixed theme taxonomy (10 themes) + heuristic classifier.

Event.category stores theme keys. UI shows emoji labels as «Темы».
Legacy category names are normalized via CATEGORY_ALIASES / LEGACY_THEME_MAP.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Stable keys stored in DB / enabled_categories JSON
THEME_AI_SOFTWARE = "ai_software"
THEME_TECHNOLOGY = "technology"
THEME_MOBILE = "mobile"
THEME_GAMING = "gaming"
THEME_SCIENCE_SPACE = "science_space"
THEME_BUSINESS = "business_finance"
THEME_CRYPTO = "crypto"
THEME_SPORT = "sport"
THEME_SECURITY = "security"
THEME_MEDIA = "media"

ALLOWED_CATEGORIES = (
    THEME_AI_SOFTWARE,
    THEME_TECHNOLOGY,
    THEME_MOBILE,
    THEME_GAMING,
    THEME_SCIENCE_SPACE,
    THEME_BUSINESS,
    THEME_CRYPTO,
    THEME_SPORT,
    THEME_SECURITY,
    THEME_MEDIA,
)

DEFAULT_CATEGORIES = list(ALLOWED_CATEGORIES)

# Short themes → 2 per keyboard row; long → 1 per row
THEME_LAYOUT_LONG = frozenset({THEME_AI_SOFTWARE, THEME_SCIENCE_SPACE, THEME_BUSINESS})


@dataclass(frozen=True, slots=True)
class ThemeMeta:
    key: str
    emoji: str
    label: str

    @property
    def display(self) -> str:
        return f"{self.emoji} {self.label}"


THEMES: dict[str, ThemeMeta] = {
    THEME_AI_SOFTWARE: ThemeMeta(THEME_AI_SOFTWARE, "🤖", "AI & Software"),
    THEME_TECHNOLOGY: ThemeMeta(THEME_TECHNOLOGY, "💻", "Technology"),
    THEME_MOBILE: ThemeMeta(THEME_MOBILE, "📱", "Mobile"),
    THEME_GAMING: ThemeMeta(THEME_GAMING, "🎮", "Gaming"),
    THEME_SCIENCE_SPACE: ThemeMeta(THEME_SCIENCE_SPACE, "🔬", "Science & Space"),
    THEME_BUSINESS: ThemeMeta(THEME_BUSINESS, "💰", "Business & Finance"),
    THEME_CRYPTO: ThemeMeta(THEME_CRYPTO, "₿", "Crypto"),
    THEME_SPORT: ThemeMeta(THEME_SPORT, "🏆", "Sport"),
    THEME_SECURITY: ThemeMeta(THEME_SECURITY, "🔐", "Security"),
    THEME_MEDIA: ThemeMeta(THEME_MEDIA, "🎬", "Media"),
}

# Legacy → new theme keys
LEGACY_THEME_MAP: dict[str, str] = {
    "AI": THEME_AI_SOFTWARE,
    "Software": THEME_AI_SOFTWARE,
    "Technology": THEME_TECHNOLOGY,
    "Hardware": THEME_TECHNOLOGY,
    "Science": THEME_SCIENCE_SPACE,
    "Business": THEME_BUSINESS,
    "Crypto": THEME_CRYPTO,
    "Sports": THEME_SPORT,
    "Sport": THEME_SPORT,
    "Security": THEME_SECURITY,
    "Gaming": THEME_GAMING,
    "Entertainment": THEME_MEDIA,
    "Politics": THEME_BUSINESS,
    "Health": THEME_SCIENCE_SPACE,
    "Other": THEME_TECHNOLOGY,
    "General": THEME_TECHNOLOGY,
}

CATEGORY_ALIASES = {
    **LEGACY_THEME_MAP,
    "Tech": THEME_TECHNOLOGY,
    "ИИ": THEME_AI_SOFTWARE,
    "Политика": THEME_BUSINESS,
    "Politics & Society": THEME_BUSINESS,
}

# Channel promo footers must not drive theme.
_FOOTER_LINE = re.compile(
    r"^\s*[▪•·●].*$|"
    r"^\s*канал\s+.+\s+в\s+[«\"].*[»\"].*$|"
    r"^\s*приложение\s+\S+\s+для\s+(ios|android).*$|"
    r"^\s*(подписывайтесь|подписаться|читайте\s+также).*$",
    re.I | re.M,
)


def _clean_blob(text: str) -> str:
    lines = []
    for line in (text or "").splitlines():
        if _FOOTER_LINE.match(line.strip()):
            continue
        lines.append(line)
    return "\n".join(lines)


_CATEGORY_RULES: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(
            r"(?<![a-zа-я])(bitcoin|ethereum|crypto|крипто\w*|блокчейн\w*|blockchain|"
            r"nft|binance|usdt|solana)",
            re.I,
        ),
        THEME_CRYPTO,
    ),
    (
        re.compile(
            r"(?<![a-zа-я])(chatgpt|openai|anthropic|claude|gemini|deepseek|llm|gpt-?\d|"
            r"нейросет\w*|machine\s*learning|генеративн\w*|artificial\s*intelligence|"
            r"ai(?![a-zа-я])|ии(?![а-я])|утилита\w*|software|saas|macos|windows|linux|"
            r"github|gitlab|vscode|cursor\b|программирован\w*|kubernetes|docker|"
            r"сторонн\w*\s+приложение|приложение\s+(для|камер|управлен))",
            re.I,
        ),
        THEME_AI_SOFTWARE,
    ),
    (
        re.compile(
            r"(?<![a-zа-я])(кибербезопасност\w*|взлом\w*|уязвим\w*|хакер\w*|ransomware|"
            r"phishing|malware|cve-|data\s*breach|утечк[аи]\s+данн\w*|vpn\b)",
            re.I,
        ),
        THEME_SECURITY,
    ),
    (
        re.compile(
            r"(?<![a-zа-я])(steam\s*deck|steam\s*machine|xbox|playstation|nintendo|"
            r"esport\w*|киберспорт\w*|dota|cs2|valorant|gaming|гейминг|"
            r"видеоигр\w*|компьютерн\w*\s+игр\w*|game\s*pass)",
            re.I,
        ),
        THEME_GAMING,
    ),
    (
        re.compile(
            r"(?<![a-zа-я])(iphone|ipad|pixel|galaxy|samsung|xiaomi|huawei|oneplus|"
            r"fold|flip|smartphone|смартфон\w*|планшет\w*|tablet|airpods|android|ios\b|"
            r"wearable|обновл[её]нн\w*\s+дизайн)",
            re.I,
        ),
        THEME_MOBILE,
    ),
    (
        re.compile(
            r"(?<![a-zа-я])(film|movie|сериал\w*|кино\b|netflix|disney|marvel|фильм\w*|"
            r"музык\w*|concert\w*|celebrity|акт[её]р\w*|режисс[её]р\w*|трейлер\w*|album\b|"
            r"медиа|media\b)",
            re.I,
        ),
        THEME_MEDIA,
    ),
    (
        re.compile(
            r"(?<![a-zа-я])(sport\w*|спорт\w*|футбол\w*|hockey|хоккей|olympic\w*|nba|fifa|"
            r"чемпионат\w*|матч\w*|tennis|теннис)",
            re.I,
        ),
        THEME_SPORT,
    ),
    (
        re.compile(
            r"(?<![a-zа-я])(space|космос\w*|nasa|spacex|rocket|спутник\w*|марс\b|"
            r"astronomy|телескоп\w*|science|наук\w*|исследован\w*|research|"
            r"физик\w*|хими\w*|биолог\w*|климат\w*|атомн\w*\s+реактор|"
            r"health|здоров\w*|медицин\w*|vaccine|вакцин\w*)",
            re.I,
        ),
        THEME_SCIENCE_SPACE,
    ),
    (
        re.compile(
            r"(?<![a-zа-я])(startup\w*|funding|инвестиц\w*|ipo\b|акци[яи]|выручк\w*|"
            r"revenue|экономик\w*|банк\w*|финтех\w*|layoff\w*|увольнен\w*|"
            r"политик\w*|president\w*|президент\w*|санкци\w*|sanction\w*|trump|путин\w*)",
            re.I,
        ),
        THEME_BUSINESS,
    ),
    (
        re.compile(
            r"(?<![a-zа-я])(nvidia|amd\b|intel|gpu|cpu|чип\w*|macbook|gadget|гаджет\w*|"
            r"hardware|technology|технолог\w*|laptop|ноутбук)",
            re.I,
        ),
        THEME_TECHNOLOGY,
    ),
]


def theme_display(key: str | None) -> str:
    meta = THEMES.get(key or "")
    if meta:
        return meta.display
    return key or THEME_TECHNOLOGY


def normalize_category(raw: str | None) -> str:
    value = (raw or "").strip()
    if not value:
        return THEME_TECHNOLOGY
    if value in ALLOWED_CATEGORIES:
        return value
    if value in CATEGORY_ALIASES:
        return CATEGORY_ALIASES[value]
    lower = {c.lower(): c for c in ALLOWED_CATEGORIES}
    if value.lower() in lower:
        return lower[value.lower()]
    # Title-case legacy like "Technology"
    if value in LEGACY_THEME_MAP:
        return LEGACY_THEME_MAP[value]
    return THEME_TECHNOLOGY


def guess_category(text: str) -> str:
    blob = _clean_blob(text or "")
    for pattern, category in _CATEGORY_RULES:
        if pattern.search(blob):
            return category
    return THEME_TECHNOLOGY


def classify_event_text(
    title: str,
    summary: str = "",
    topic: str = "",
    *,
    current: str | None = None,
) -> str:
    for blob in (
        f"{title}\n{topic}",
        f"{title}\n{summary}\n{topic}",
    ):
        guessed = guess_category(blob)
        if guessed:
            return guessed
    return normalize_category(current)


def default_theme_weights() -> dict[str, int]:
    return {k: 3 for k in ALLOWED_CATEGORIES}


def migrate_enabled_list(raw: list | None) -> list[str]:
    """Map legacy enabled list to theme keys; empty → all enabled."""
    if not raw:
        return list(DEFAULT_CATEGORIES)
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        key = normalize_category(str(item))
        if key in ALLOWED_CATEGORIES and key not in seen:
            seen.add(key)
            out.append(key)
    return out or list(DEFAULT_CATEGORIES)
