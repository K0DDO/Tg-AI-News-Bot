"""Category taxonomy tests — new theme set."""

from app.services.categories import (
    THEME_BUSINESS,
    THEME_GAMING,
    THEME_OTHER,
    THEME_POLITICS,
    THEME_SCIENCE,
    THEME_SOFTWARE,
    THEME_TECHNOLOGY,
    THEME_TOOLS,
    THEME_WORK,
    classify_event_text,
    guess_category,
    normalize_category,
)


def test_politics_guess():
    assert guess_category("Путин встретился с президентом Франции в Кремле") == THEME_POLITICS
    assert guess_category("New US sanctions against Russia announced by White House") == THEME_POLITICS


def test_normalize_legacy():
    assert normalize_category("General") == THEME_OTHER
    assert normalize_category("Politics") == THEME_POLITICS
    assert normalize_category("Other") == THEME_OTHER
    assert normalize_category("ИИ") == THEME_SOFTWARE
    assert normalize_category("ai_software") == THEME_SOFTWARE
    assert normalize_category("Technology") == THEME_TECHNOLOGY
    assert normalize_category("business_finance") == THEME_BUSINESS
    assert normalize_category("mobile") == THEME_SOFTWARE


def test_tools_and_gaming():
    assert guess_category("OpenAI выпустила новую модель ChatGPT") == THEME_TOOLS
    assert guess_category("Valve анонсировала новую Steam Machine для геймеров") == THEME_GAMING


def test_utility_is_tools():
    text = "Найдена бесплатная утилита для анализа USB-C кабелей на macOS"
    assert guess_category(text) == THEME_TOOLS
    assert classify_event_text(text, current=THEME_TECHNOLOGY) == THEME_TOOLS


def test_pixel_phone_is_software():
    text = "Pixel 11 Pro Fold получит обновлённый дизайн"
    assert guess_category(text) == THEME_SOFTWARE
    assert classify_event_text(text, current="Hardware") == THEME_SOFTWARE


def test_gpu_is_technology():
    assert guess_category("NVIDIA представила новый GPU RTX 6090") == THEME_TECHNOLOGY


def test_channel_footer_does_not_force_software():
    title = "Силы ПВО сбили еще три беспилотника, летевших на Москву"
    summary = (
        f"{title}\n\n"
        "▪Канал РБК в «Максе»\n"
        "▪Приложение РБК для iOS и Android"
    )
    cat = classify_event_text(title, summary)
    assert cat not in (THEME_SOFTWARE, THEME_TOOLS)
    assert cat == THEME_POLITICS


def test_sanctions_are_politics():
    assert guess_category("Евросоюз ввел санкции против VK и Max") == THEME_POLITICS


def test_unknown_is_other():
    assert guess_category("Сегодня хорошая погода в городе") == THEME_OTHER
    assert normalize_category("") == THEME_OTHER
    assert normalize_category("TotallyUnknownLabel") == THEME_OTHER


def test_business_without_politics():
    assert guess_category("Стартап привлек $50M funding на IPO") == THEME_BUSINESS


def test_work_category():
    assert guess_category("Открыта вакансия Python-разработчика, удалёнка, зарплата") == THEME_WORK


def test_science():
    assert guess_category("NASA запустила новый телескоп для исследования Марса") == THEME_SCIENCE
