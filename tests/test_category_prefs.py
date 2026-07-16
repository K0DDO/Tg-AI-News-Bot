"""Category preference toggle must stick (no auto re-enable)."""

from types import SimpleNamespace

from app.services.categories import DEFAULT_CATEGORIES, THEME_SOFTWARE, THEME_TECHNOLOGY
from app.services.preferences import PreferencesService


def test_ensure_categories_does_not_readd_disabled():
    settings = SimpleNamespace(enabled_categories=[THEME_SOFTWARE])
    PreferencesService._ensure_categories(settings)
    assert settings.enabled_categories == [THEME_SOFTWARE]


def test_ensure_categories_empty_gets_defaults():
    settings = SimpleNamespace(enabled_categories=[])
    PreferencesService._ensure_categories(settings)
    assert settings.enabled_categories == DEFAULT_CATEGORIES


def test_ensure_categories_migrates_legacy_and_dedupes():
    from app.services.categories import THEME_OTHER

    settings = SimpleNamespace(enabled_categories=["AI", "Software", "General", "Technology"])
    PreferencesService._ensure_categories(settings)
    assert settings.enabled_categories == [THEME_SOFTWARE, THEME_OTHER, THEME_TECHNOLOGY]
