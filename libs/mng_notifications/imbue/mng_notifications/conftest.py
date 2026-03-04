"""Test fixtures for mng-notifications.

Uses shared plugin test fixtures from mng for common setup (plugin manager,
environment isolation, etc.).
"""

import pytest

from imbue.mng.utils.plugin_testing import register_plugin_test_fixtures

register_plugin_test_fixtures(globals())


@pytest.fixture()
def fake_platform_darwin(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make platform.system() return "Darwin" in the notifier module."""
    monkeypatch.setattr("imbue.mng_notifications.notifier.platform.system", lambda: "Darwin")


@pytest.fixture()
def fake_platform_linux(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make platform.system() return "Linux" in the notifier module."""
    monkeypatch.setattr("imbue.mng_notifications.notifier.platform.system", lambda: "Linux")


@pytest.fixture()
def fake_platform_unsupported(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make platform.system() return "Windows" in the notifier module."""
    monkeypatch.setattr("imbue.mng_notifications.notifier.platform.system", lambda: "Windows")
