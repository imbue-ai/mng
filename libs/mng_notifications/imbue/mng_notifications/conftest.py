"""Test fixtures for mng-notifications.

Uses shared plugin test fixtures from mng for common setup (plugin manager,
environment isolation, etc.).
"""

import pytest

from imbue.mng.utils.plugin_testing import register_plugin_test_fixtures
from imbue.mng_notifications.testing import FakePlatform

register_plugin_test_fixtures(globals())


@pytest.fixture()
def fake_platform(monkeypatch: pytest.MonkeyPatch) -> FakePlatform:
    """Patch platform.system() in the notifier module to return a controlled value."""
    return FakePlatform(monkeypatch)
