"""Category taxonomy tests — 10 theme keys."""

from app.services.categories import (
    THEME_AI_SOFTWARE,
    THEME_BUSINESS,
    THEME_GAMING,
    THEME_MOBILE,
    THEME_TECHNOLOGY,
    classify_event_text,
    guess_category,
    normalize_category,
)


def test_politics_guess():
    assert guess_category("Путин встретился с президентом Франции в Кремле") == THEME_BUSINESS
    assert guess_category("New US sanctions against Russia announced by White House") == THEME_BUSINESS


def test_normalize_general():
    assert normalize_category("General") == THEME_TECHNOLOGY
    assert normalize_category("Politics") == THEME_BUSINESS
    assert normalize_category("ИИ") == THEME_AI_SOFTWARE
    assert normalize_category("ai_software") == THEME_AI_SOFTWARE
    assert normalize_category("Technology") == THEME_TECHNOLOGY


def test_ai_and_gaming():
    assert guess_category("OpenAI выпустила новую модель ChatGPT") == THEME_AI_SOFTWARE
    assert guess_category("Valve анонсировала новую Steam Machine для геймеров") == THEME_GAMING


def test_utility_is_ai_software_not_technology():
    text = "Найдена бесплатная утилита для анализа USB-C кабелей на macOS"
    assert guess_category(text) == THEME_AI_SOFTWARE
    assert classify_event_text(text, current=THEME_TECHNOLOGY) == THEME_AI_SOFTWARE


def test_pixel_phone_is_mobile():
    text = "Pixel 11 Pro Fold получит обновлённый дизайн"
    assert guess_category(text) == THEME_MOBILE
    assert classify_event_text(text, current="Hardware") == THEME_MOBILE


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
    assert cat not in (THEME_AI_SOFTWARE, THEME_MOBILE)
    assert cat == THEME_TECHNOLOGY


def test_sanctions_are_business():
    assert guess_category("Евросоюз ввел санкции против VK и Max") == THEME_BUSINESS
