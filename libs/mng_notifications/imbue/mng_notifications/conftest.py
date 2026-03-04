"""Test fixtures for mng-notifications.

Uses shared plugin test fixtures from mng for common setup (plugin manager,
environment isolation, etc.) and defines notifications-specific fixtures below.
"""

import subprocess
from typing import Any

import pytest

from imbue.mng.utils.plugin_testing import register_plugin_test_fixtures

register_plugin_test_fixtures(globals())

_NOTIFICATION_COMMANDS = ("terminal-notifier", "notify-send")


@pytest.fixture()
def fake_subprocess_run(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """Intercept notification subprocess calls and record them.

    Non-notification commands (e.g. tmux) pass through to the real subprocess.run.
    """
    calls: list[list[str]] = []
    real_run = subprocess.run

    def _recording_run(cmd: list[str], **kwargs: Any) -> Any:
        if cmd and cmd[0] in _NOTIFICATION_COMMANDS:
            calls.append(cmd)
            return None
        return real_run(cmd, **kwargs)

    monkeypatch.setattr("subprocess.run", _recording_run)
    return calls


@pytest.fixture()
def fake_subprocess_run_raising(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make notification subprocess calls raise FileNotFoundError."""
    real_run = subprocess.run

    def _raising_run(cmd: list[str], **kwargs: Any) -> Any:
        if cmd and cmd[0] in _NOTIFICATION_COMMANDS:
            raise FileNotFoundError(f"{cmd[0]} not found")
        return real_run(cmd, **kwargs)

    monkeypatch.setattr("subprocess.run", _raising_run)


@pytest.fixture()
def fake_subprocess_run_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make notification subprocess calls raise TimeoutExpired."""
    real_run = subprocess.run

    def _timeout_run(cmd: list[str], **kwargs: Any) -> Any:
        if cmd and cmd[0] in _NOTIFICATION_COMMANDS:
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=10)
        return real_run(cmd, **kwargs)

    monkeypatch.setattr("subprocess.run", _timeout_run)
