"""Category preference toggle must stick (no auto re-enable)."""

from types import SimpleNamespace

from app.services.preferences import PreferencesService


def test_ensure_categories_does_not_readd_disabled():
    settings = SimpleNamespace(enabled_categories=["AI", "Software"])
    PreferencesService._ensure_categories(settings)
    assert settings.enabled_categories == ["AI", "Software"]


def test_ensure_categories_empty_gets_defaults():
    from app.services.categories import DEFAULT_CATEGORIES

    settings = SimpleNamespace(enabled_categories=[])
    PreferencesService._ensure_categories(settings)
    assert settings.enabled_categories == DEFAULT_CATEGORIES


def test_ensure_categories_drops_unknown():
    settings = SimpleNamespace(enabled_categories=["AI", "General", "Technology"])
    PreferencesService._ensure_categories(settings)
    assert settings.enabled_categories == ["AI", "Technology"]
