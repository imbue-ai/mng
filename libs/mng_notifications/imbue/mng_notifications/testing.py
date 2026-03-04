"""Non-fixture test utilities for mng-notifications."""

from collections.abc import Callable
from typing import Any

import pytest

from imbue.mng.api.list import ListResult


def patch_platform(monkeypatch: pytest.MonkeyPatch, system: str) -> None:
    """Set a fake platform.system() in the notifier module."""
    monkeypatch.setattr("imbue.mng_notifications.notifier.platform.system", lambda: system)


def patch_list_agents(monkeypatch: pytest.MonkeyPatch, fn: Callable[..., ListResult | None]) -> None:
    """Replace list_agents in the watcher module."""
    monkeypatch.setattr("imbue.mng_notifications.watcher.list_agents", fn)


def patch_list_agents_returns(monkeypatch: pytest.MonkeyPatch, result: ListResult) -> None:
    """Make list_agents return a fixed result."""
    patch_list_agents(monkeypatch, lambda mng_ctx, **kwargs: result)


def patch_list_agents_raises(monkeypatch: pytest.MonkeyPatch, error: BaseException) -> None:
    """Make list_agents raise an error."""

    def _raise(mng_ctx: Any, **kwargs: Any) -> None:
        raise error

    patch_list_agents(monkeypatch, _raise)
