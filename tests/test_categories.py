"""Category taxonomy tests."""

from app.services.categories import classify_event_text, guess_category, normalize_category


def test_politics_guess():
    assert guess_category("Путин встретился с президентом Франции в Кремле") == "Politics"
    assert guess_category("New US sanctions against Russia announced by White House") == "Politics"


def test_normalize_general():
    assert normalize_category("General") == "Other"
    assert normalize_category("Politics") == "Politics"
    assert normalize_category("ИИ") == "AI"


def test_ai_and_gaming():
    assert guess_category("OpenAI выпустила новую модель ChatGPT") == "AI"
    assert guess_category("Valve анонсировала новую Steam Machine для геймеров") == "Gaming"


def test_utility_is_software_not_technology():
    text = "Найдена бесплатная утилита для анализа USB-C кабелей на macOS"
    assert guess_category(text) == "Software"
    assert classify_event_text(text, current="Technology") == "Software"


def test_pixel_phone_is_technology_not_hardware():
    text = "Pixel 11 Pro Fold получит обновлённый дизайн"
    assert guess_category(text) == "Technology"
    assert classify_event_text(text, current="Hardware") == "Technology"


def test_gpu_stays_hardware():
    assert guess_category("NVIDIA представила новый GPU RTX 6090") == "Hardware"


def test_channel_footer_does_not_force_software():
    title = "Силы ПВО сбили еще три беспилотника, летевших на Москву"
    summary = (
        f"{title}\n\n"
        "▪Канал РБК в «Максе»\n"
        "▪Приложение РБК для iOS и Android"
    )
    assert classify_event_text(title, summary) == "Politics"


def test_sanctions_are_politics():
    assert guess_category("Евросоюз ввел санкции против VK и Max") == "Politics"
