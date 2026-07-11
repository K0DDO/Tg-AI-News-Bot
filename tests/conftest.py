import pytest


@pytest.fixture
def any_settings_overrides(monkeypatch):
    """Helper hook for tests that need env overrides."""
    return monkeypatch
