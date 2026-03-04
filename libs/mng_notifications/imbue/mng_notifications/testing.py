from collections.abc import Callable
from typing import Any

import pytest

from imbue.mng.api.list import ListResult
from imbue.mng.errors import MngError


def patch_platform(monkeypatch: pytest.MonkeyPatch, system: str) -> None:
    """Set a fake platform.system() in the notifier module."""
    monkeypatch.setattr("imbue.mng_notifications.notifier.platform.system", lambda: system)


def patch_list_agents(monkeypatch: pytest.MonkeyPatch, fn: Callable[..., ListResult | None]) -> None:
    """Replace list_agents in the watcher module."""
    monkeypatch.setattr("imbue.mng_notifications.watcher.list_agents", fn)


def patch_list_agents_returns(monkeypatch: pytest.MonkeyPatch, result: ListResult) -> None:
    """Make list_agents return a fixed result."""
    patch_list_agents(monkeypatch, lambda *_args, **_kwargs: result)


def _raise_mng_error(*_args: Any, **_kwargs: Any) -> None:
    raise MngError("poll failed")


def patch_list_agents_raises_mng_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make list_agents raise MngError."""
    patch_list_agents(monkeypatch, _raise_mng_error)
