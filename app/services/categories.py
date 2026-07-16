"""Fixed theme taxonomy + heuristic classifier.

Event.category stores theme keys. UI shows emoji labels as «Темы».
Legacy category names are normalized via CATEGORY_ALIASES / LEGACY_THEME_MAP.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Stable keys stored in DB / enabled_categories JSON
THEME_WORK = "work"
THEME_TECHNOLOGY = "technology"
THEME_TOOLS = "tools"
THEME_GAMING = "gaming"
THEME_SOFTWARE = "software"
THEME_BUSINESS = "business"
THEME_SCIENCE = "science"
THEME_POLITICS = "politics"
THEME_OTHER = "other"

# Legacy keys kept for normalize() only
_LEGACY_AI = "ai_software"
_LEGACY_MOBILE = "mobile"
_LEGACY_SCIENCE = "science_space"
_LEGACY_BUSINESS = "business_finance"
_LEGACY_CRYPTO = "crypto"
_LEGACY_SPORT = "sport"
_LEGACY_SECURITY = "security"
_LEGACY_MEDIA = "media"

ALLOWED_CATEGORIES = (
    THEME_WORK,
    THEME_TECHNOLOGY,
    THEME_TOOLS,
    THEME_GAMING,
    THEME_SOFTWARE,
    THEME_BUSINESS,
    THEME_SCIENCE,
    THEME_POLITICS,
    THEME_OTHER,
)

# Main themes first; politics/other shown in a secondary block in the keyboard
PRIMARY_THEMES = (
    THEME_WORK,
    THEME_TECHNOLOGY,
    THEME_TOOLS,
    THEME_GAMING,
    THEME_SOFTWARE,
    THEME_BUSINESS,
    THEME_SCIENCE,
)
SECONDARY_THEMES = (THEME_POLITICS, THEME_OTHER)

# Themes that existed before the product refresh — used to auto-enable new ones
_LEGACY_FULL_THEMES = frozenset(
    {
        _LEGACY_AI,
        THEME_TECHNOLOGY,
        _LEGACY_MOBILE,
        THEME_GAMING,
        _LEGACY_SCIENCE,
        _LEGACY_BUSINESS,
        _LEGACY_CRYPTO,
        _LEGACY_SPORT,
        _LEGACY_SECURITY,
        _LEGACY_MEDIA,
        THEME_POLITICS,
        THEME_OTHER,
    }
)

DEFAULT_CATEGORIES = list(ALLOWED_CATEGORIES)

# Long labels → 1 per keyboard row
THEME_LAYOUT_LONG = frozenset({THEME_TECHNOLOGY, THEME_BUSINESS, THEME_SOFTWARE})


@dataclass(frozen=True, slots=True)
class ThemeMeta:
    key: str
    emoji: str
    label: str

    @property
    def display(self) -> str:
        return f"{self.emoji} {self.label}"


THEMES: dict[str, ThemeMeta] = {
    THEME_WORK: ThemeMeta(THEME_WORK, "💼", "Работа"),
    THEME_TECHNOLOGY: ThemeMeta(THEME_TECHNOLOGY, "💻", "Технологии"),
    THEME_TOOLS: ThemeMeta(THEME_TOOLS, "🛠", "Инструменты"),
    THEME_GAMING: ThemeMeta(THEME_GAMING, "🎮", "Игры"),
    THEME_SOFTWARE: ThemeMeta(THEME_SOFTWARE, "📱", "Софт"),
    THEME_BUSINESS: ThemeMeta(THEME_BUSINESS, "📈", "Бизнес"),
    THEME_SCIENCE: ThemeMeta(THEME_SCIENCE, "🔬", "Наука"),
    THEME_POLITICS: ThemeMeta(THEME_POLITICS, "🏛", "Политика"),
    THEME_OTHER: ThemeMeta(THEME_OTHER, "🎨", "Разное"),
}

# Legacy → new theme keys
LEGACY_THEME_MAP: dict[str, str] = {
    "AI": THEME_SOFTWARE,
    "Software": THEME_SOFTWARE,
    "Technology": THEME_TECHNOLOGY,
    "Hardware": THEME_TECHNOLOGY,
    "Science": THEME_SCIENCE,
    "Business": THEME_BUSINESS,
    "Crypto": THEME_BUSINESS,
    "Sports": THEME_OTHER,
    "Sport": THEME_OTHER,
    "Security": THEME_TECHNOLOGY,
    "Gaming": THEME_GAMING,
    "Entertainment": THEME_OTHER,
    "Politics": THEME_POLITICS,
    "Health": THEME_SCIENCE,
    "Other": THEME_OTHER,
    "General": THEME_OTHER,
    "Work": THEME_WORK,
    "Tools": THEME_TOOLS,
    "Mobile": THEME_SOFTWARE,
    _LEGACY_AI: THEME_SOFTWARE,
    _LEGACY_MOBILE: THEME_SOFTWARE,
    _LEGACY_SCIENCE: THEME_SCIENCE,
    _LEGACY_BUSINESS: THEME_BUSINESS,
    _LEGACY_CRYPTO: THEME_BUSINESS,
    _LEGACY_SPORT: THEME_OTHER,
    _LEGACY_SECURITY: THEME_TECHNOLOGY,
    _LEGACY_MEDIA: THEME_OTHER,
    "ai_software": THEME_SOFTWARE,
    "mobile": THEME_SOFTWARE,
    "science_space": THEME_SCIENCE,
    "business_finance": THEME_BUSINESS,
    "crypto": THEME_BUSINESS,
    "sport": THEME_OTHER,
    "security": THEME_TECHNOLOGY,
    "media": THEME_OTHER,
}

CATEGORY_ALIASES = {
    **LEGACY_THEME_MAP,
    "Tech": THEME_TECHNOLOGY,
    "ИИ": THEME_SOFTWARE,
    "Политика": THEME_POLITICS,
    "Politics & Society": THEME_POLITICS,
    "Другое": THEME_OTHER,
    "Разное": THEME_OTHER,
    "Misc": THEME_OTHER,
    "Unknown": THEME_OTHER,
    "Работа": THEME_WORK,
    "Инструменты": THEME_TOOLS,
    "Софт": THEME_SOFTWARE,
    "Бизнес": THEME_BUSINESS,
    "Наука": THEME_SCIENCE,
    "Игры": THEME_GAMING,
    "Технологии": THEME_TECHNOLOGY,
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
            r"(?<![a-zа-я])(ваканси\w*|удалёнк\w*|удаленк\w*|релокац\w*|зарплат\w*|"
            r"job\s*offer|hiring|карьера\w*|собеседован\w*|hr\b|резюме\b|"
            r"work\s*from\s*home|remote\s*work|layoff\w*|увольнен\w*)",
            re.I,
        ),
        THEME_WORK,
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
            r"(?<![a-zа-я])(политик\w*|politics|president\w*|президент\w*|санкци\w*|"
            r"sanction\w*|trump|путин\w*|правительств\w*|парламент\w*|госдум\w*|"
            r"выбор\w*|election\w*|minister\w*|министр\w*|дипломат\w*|кремл\w*|"
            r"white\s*house|нато\b|nato\b|военн\w*|войн\w*|пво\b|беспилотник\w*|"
            r"drone\w*|missile\w*|ракет\w*|геополитик\w*)",
            re.I,
        ),
        THEME_POLITICS,
    ),
    (
        re.compile(
            r"(?<![a-zа-я])(chatgpt|openai|anthropic|claude|gemini|deepseek|llm|gpt-?\d|"
            r"нейросет\w*|machine\s*learning|генеративн\w*|artificial\s*intelligence|"
            r"ai(?![a-zа-я])|ии(?![а-я])|vscode|cursor\b|github|gitlab|"
            r"утилита\w*|cli\b|плагин\w*|plugin\w*|extension\w*|инструмент\w*|"
            r"devtools|jetbrains|figma)",
            re.I,
        ),
        THEME_TOOLS,
    ),
    (
        re.compile(
            r"(?<![a-zа-я])(iphone|ipad|pixel|galaxy|samsung|xiaomi|huawei|oneplus|"
            r"fold|flip|smartphone|смартфон\w*|планшет\w*|tablet|airpods|android|ios\b|"
            r"wearable|приложение\w*|app\s*store|google\s*play|saas|macos|windows|linux|"
            r"сторонн\w*\s+приложение|software|софт\b)",
            re.I,
        ),
        THEME_SOFTWARE,
    ),
    (
        re.compile(
            r"(?<![a-zа-я])(кибербезопасност\w*|взлом\w*|уязвим\w*|хакер\w*|ransomware|"
            r"phishing|malware|cve-|data\s*breach|утечк[аи]\s+данн\w*|vpn\b|"
            r"nvidia|amd\b|intel|gpu|cpu|чип\w*|macbook|gadget|гаджет\w*|"
            r"hardware|technology|технолог\w*|laptop|ноутбук|kubernetes|docker)",
            re.I,
        ),
        THEME_TECHNOLOGY,
    ),
    (
        re.compile(
            r"(?<![a-zа-я])(space|космос\w*|nasa|spacex|rocket|спутник\w*|марс\b|"
            r"astronomy|телескоп\w*|science|наук\w*|исследован\w*|research|"
            r"физик\w*|хими\w*|биолог\w*|климат\w*|атомн\w*\s+реактор|"
            r"health|здоров\w*|медицин\w*|vaccine|вакцин\w*)",
            re.I,
        ),
        THEME_SCIENCE,
    ),
    (
        re.compile(
            r"(?<![a-zа-я])(startup\w*|funding|инвестиц\w*|ipo\b|акци[яи]|выручк\w*|"
            r"revenue|экономик\w*|банк\w*|финтех\w*|bitcoin|ethereum|crypto|"
            r"крипто\w*|блокчейн\w*|blockchain|nft|binance)",
            re.I,
        ),
        THEME_BUSINESS,
    ),
]


def theme_display(key: str | None, lang: str | None = None) -> str:
    meta = THEMES.get(normalize_category(key) if key else THEME_OTHER)
    if meta:
        if lang and lang != "ru":
            try:
                from app.bot.i18n import t

                label = t(lang, f"theme_{meta.key}")
                if label and label != f"theme_{meta.key}":
                    return f"{meta.emoji} {label}"
            except Exception:
                pass
        return meta.display
    return key or THEME_OTHER


def normalize_category(raw: str | None) -> str:
    value = (raw or "").strip()
    if not value:
        return THEME_OTHER
    if value in ALLOWED_CATEGORIES:
        return value
    if value in CATEGORY_ALIASES:
        return CATEGORY_ALIASES[value]
    lower = {c.lower(): c for c in ALLOWED_CATEGORIES}
    if value.lower() in lower:
        return lower[value.lower()]
    if value in LEGACY_THEME_MAP:
        return LEGACY_THEME_MAP[value]
    return THEME_OTHER


def guess_category(text: str) -> str:
    blob = _clean_blob(text or "")
    for pattern, category in _CATEGORY_RULES:
        if pattern.search(blob):
            return category
    return THEME_OTHER


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
        if guessed and guessed != THEME_OTHER:
            return guessed
        if guessed == THEME_OTHER and blob.strip():
            continue
    if current:
        return normalize_category(current)
    return THEME_OTHER


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
    # Users who had a full legacy set get new primary themes auto-enabled
    if len(seen) >= 8:
        for key in ALLOWED_CATEGORIES:
            if key not in seen:
                seen.add(key)
                out.append(key)
    return out or list(DEFAULT_CATEGORIES)
