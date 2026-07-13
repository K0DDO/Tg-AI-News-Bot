"""Shared news category taxonomy + heuristic guesser.

Semantics:
  AI          — models, LLMs, generative AI
  Software    — apps, utilities, OS software, tools, SaaS
  Hardware    — chips, GPUs, CPUs, storage, cables, silicon/components
  Technology  — phones, tablets, consumer gadgets, product design
  Science     — research, space, climate
  Business    — markets, funding, earnings
  Politics    — government, elections, sanctions, war
  …           — Entertainment, Sports, Health, Security, Crypto, Gaming, Other
"""

from __future__ import annotations

import re

ALLOWED_CATEGORIES = (
    "AI",
    "Technology",
    "Hardware",
    "Software",
    "Science",
    "Business",
    "Politics",
    "Entertainment",
    "Sports",
    "Health",
    "Security",
    "Crypto",
    "Gaming",
    "Other",
)

CATEGORY_ALIASES = {
    "General": "Other",
    "general": "Other",
    "Politics & Society": "Politics",
    "Политика": "Politics",
    "ИИ": "AI",
    "Tech": "Technology",
    "Education": "Other",
}

DEFAULT_CATEGORIES = list(ALLOWED_CATEGORIES)

# Channel promo footers (e.g. RBC "▪Приложение РБК для iOS") must not drive category.
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


# More specific rules first. Phones/gadgets → Technology, not Hardware.
# Russian stems use \w* so "санкции"/"политика" match (plain \b after stem fails).
_CATEGORY_RULES: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(
            r"(?<![a-zа-я])(chatgpt|openai|anthropic|claude|gemini|deepseek|llm|gpt-?\d|"
            r"нейросет\w*|machine\s*learning|генеративн\w*|artificial\s*intelligence|"
            r"ai(?![a-zа-я])|ии(?![а-я]))",
            re.I,
        ),
        "AI",
    ),
    (
        re.compile(
            r"(?<![a-zа-я])(bitcoin|ethereum|crypto|крипто\w*|блокчейн\w*|blockchain|"
            r"nft|binance|usdt|solana)",
            re.I,
        ),
        "Crypto",
    ),
    (
        re.compile(
            r"(?<![a-zа-я])(политик\w*|president\w*|президент\w*|госдум\w*|парламент\w*|"
            r"выборы|election\w*|sanction\w*|санкци\w*|мид\b|мид\s|правительств\w*|"
            r"minister\w*|министр\w*|congress|сенат\w*|сенатор\w*|nato|нато|"
            r"войн\w*|trump|путин\w*|байден\w*|зеленск\w*|кремл\w*|белы[йи]\s+дом|"
            r"white\s+house|закон\s+о|законопроект\w*|депутат\w*|оппозици\w*|"
            r"премьер\w*|пво\b|беспилотник\w*|миноборон\w*|вооруж[её]нн\w*\s+сил|"
            r"вс\s+росси\w*|удар\w*\s+высокоточн|ракетн\w*\s+удар)",
            re.I,
        ),
        "Politics",
    ),
    (
        re.compile(
            r"(?<![a-zа-я])(кибербезопасност\w*|взлом\w*|уязвим\w*|хакер\w*|ransomware|"
            r"phishing|malware|cve-|data\s*breach|утечк[аи]\s+данн\w*)",
            re.I,
        ),
        "Security",
    ),
    (
        re.compile(
            r"(?<![a-zа-я])(steam\s*deck|steam\s*machine|xbox|playstation|nintendo|"
            r"esport\w*|киберспорт\w*|dota|cs2|valorant|gaming|гейминг|"
            r"видеоигр\w*|компьютерн\w*\s+игр\w*|game\s*pass)",
            re.I,
        ),
        "Gaming",
    ),
    (
        re.compile(
            r"(?<![a-zа-я])(film|movie|сериал\w*|кино\b|netflix|disney|marvel|фильм\w*|"
            r"музык\w*|concert\w*|celebrity|акт[её]р\w*|режисс[её]р\w*|трейлер\w*|album\b)",
            re.I,
        ),
        "Entertainment",
    ),
    (
        re.compile(
            r"(?<![a-zа-я])(sport\w*|спорт\w*|футбол\w*|hockey|хоккей|olympic\w*|nba|fifa|"
            r"чемпионат\w*|матч\w*|tennis|теннис)",
            re.I,
        ),
        "Sports",
    ),
    (
        re.compile(
            r"(?<![a-zа-я])(health|здоров\w*|медицин\w*|vaccine|вакцин\w*|covid|"
            r"hospital|клиник\w*|лекарств\w*|pharma|болезн\w*)",
            re.I,
        ),
        "Health",
    ),
    # Software BEFORE Technology/Hardware — utilities, apps, OS tools.
    # Avoid bare "приложение" (RBC footers / "appendix") and bare "инструмент".
    (
        re.compile(
            r"(?<![a-zа-я])(утилита\w*|utility|devtools?|сторонн\w*\s+приложение|"
            r"мобильн\w*\s+приложение|приложение\s+(для|камер|управлен|удал[её]н)|"
            r"app\s*store|software|saas|плагин\w*|plugin\w*|browser\s*extension|"
            r"macos|windows|linux|devops|kubernetes|docker|github|gitlab|"
            r"ide\b|vscode|cursor\b|программирован\w*|open[\s-]?source|"
            r"sdk\b|rest\s*api|драйвер(?!\s+gpu)|программа\s+(для|установ))",
            re.I,
        ),
        "Software",
    ),
    # Hardware = components / silicon / peripherals — NOT phones
    (
        re.compile(
            r"(?<![a-zа-я])(nvidia|amd\b|intel|gpu|cpu|чип\w*|chipset|процессор\w*|"
            r"полупроводник\w*|rtx|cuda|ssd|nvme|ddr\d|motherboard|материнск\w*|"
            r"видеокарт\w*|кабел\w*|cable|usb[\s\-]?c|usbc|разъ[её]м\w*|адаптер\w*|"
            r"adapter|hardware|комплектующ\w*|железа|tpu|npu)",
            re.I,
        ),
        "Hardware",
    ),
    (
        re.compile(
            r"(?<![a-zа-я])(space|космос\w*|nasa|spacex|rocket|спутник\w*|марс\b|"
            r"astronomy|телескоп\w*|science|наук\w*|исследован\w*|research|"
            r"физик\w*|хими\w*|биолог\w*|климат\w*|атомн\w*\s+реактор)",
            re.I,
        ),
        "Science",
    ),
    (
        re.compile(
            r"(?<![a-zа-я])(startup\w*|funding|инвестиц\w*|ipo\b|акци[яи]|выручк\w*|"
            r"revenue|экономик\w*|банк\w*|финтех\w*|layoff\w*|увольнен\w*|"
            r"квартальн\w*\s+отч[её]т)",
            re.I,
        ),
        "Business",
    ),
    # Consumer gadgets / phones / product design
    (
        re.compile(
            r"(?<![a-zа-я])(iphone|ipad|macbook|pixel|galaxy|samsung|xiaomi|huawei|"
            r"oneplus|fold|flip|smartphone|смартфон\w*|планшет\w*|tablet|gadget|"
            r"гаджет\w*|wearable|airpods|vision\s*pro|android|ios\b|"
            r"обновл[её]нн\w*\s+дизайн|consumer\s*electronics)",
            re.I,
        ),
        "Technology",
    ),
]


def normalize_category(raw: str | None) -> str:
    value = (raw or "").strip()
    if not value:
        return "Other"
    if value in CATEGORY_ALIASES:
        value = CATEGORY_ALIASES[value]
    if value in ALLOWED_CATEGORIES:
        return value
    lower = {c.lower(): c for c in ALLOWED_CATEGORIES}
    if value.lower() in lower:
        return lower[value.lower()]
    return "Other"


def guess_category(text: str) -> str:
    blob = _clean_blob(text or "")
    for pattern, category in _CATEGORY_RULES:
        if pattern.search(blob):
            return category
    return "Other"


def classify_event_text(
    title: str,
    summary: str = "",
    topic: str = "",
    *,
    current: str | None = None,
) -> str:
    """
    Pick the best category for an event.
    Prefer title/topic signals; fall back to cleaned summary; else keep current.
    """
    for blob in (
        f"{title}\n{topic}",
        f"{title}\n{summary}\n{topic}",
    ):
        guessed = guess_category(blob)
        if guessed != "Other":
            return guessed
    return normalize_category(current)
