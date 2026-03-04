"""Non-fixture test utilities for mng-notifications."""

import pytest


class FakePlatform:
    """Helper to set a fake platform for notifier tests."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._monkeypatch = monkeypatch

    def set(self, system: str) -> None:
        self._monkeypatch.setattr("imbue.mng_notifications.notifier.platform.system", lambda: system)
