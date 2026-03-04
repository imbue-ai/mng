"""Unit tests for the notification module."""

import subprocess
from typing import Any

import pytest

from imbue.mng_notifications.config import NotificationsPluginConfig
from imbue.mng_notifications.notifier import _send_linux_notification
from imbue.mng_notifications.notifier import _send_macos_notification
from imbue.mng_notifications.notifier import build_execute_command
from imbue.mng_notifications.notifier import send_desktop_notification


def _config(
    terminal_app: str | None = None,
    custom_terminal_command: str | None = None,
) -> NotificationsPluginConfig:
    return NotificationsPluginConfig(
        terminal_app=terminal_app,
        custom_terminal_command=custom_terminal_command,
    )


# --- build_execute_command ---


def test_build_execute_command_no_config() -> None:
    """No terminal_app or custom_command returns None."""
    assert build_execute_command("agent-x", _config()) is None


def test_build_execute_command_custom_command() -> None:
    """custom_terminal_command is used with MNG_AGENT_NAME export."""
    result = build_execute_command("agent-x", _config(custom_terminal_command="my-cmd $MNG_AGENT_NAME"))
    assert result is not None
    assert "MNG_AGENT_NAME=agent-x" in result
    assert "my-cmd $MNG_AGENT_NAME" in result


def test_build_execute_command_custom_command_with_quotes_in_name() -> None:
    """Agent names with single quotes are properly escaped via shlex.quote."""
    result = build_execute_command("it's-agent", _config(custom_terminal_command="my-cmd"))
    assert result is not None
    assert "MNG_AGENT_NAME=" in result
    assert "my-cmd" in result


def test_build_execute_command_custom_takes_precedence() -> None:
    """custom_terminal_command takes precedence over terminal_app."""
    result = build_execute_command(
        "agent-x",
        _config(terminal_app="iTerm", custom_terminal_command="my-cmd"),
    )
    assert result is not None
    assert "my-cmd" in result
    assert "iTerm" not in result


def test_build_execute_command_iterm() -> None:
    result = build_execute_command("agent-x", _config(terminal_app="iTerm"))
    assert result is not None
    assert "iTerm2" in result
    assert "mng connect" in result
    assert "agent-x" in result


def test_build_execute_command_iterm2() -> None:
    result = build_execute_command("agent-x", _config(terminal_app="iterm2"))
    assert result is not None
    assert "iTerm2" in result


def test_build_execute_command_terminal_app() -> None:
    result = build_execute_command("agent-x", _config(terminal_app="Terminal"))
    assert result is not None
    assert '"Terminal"' in result
    assert "do script" in result


def test_build_execute_command_wezterm() -> None:
    result = build_execute_command("agent-x", _config(terminal_app="WezTerm"))
    assert result is not None
    assert "wezterm cli spawn" in result


def test_build_execute_command_kitty() -> None:
    result = build_execute_command("agent-x", _config(terminal_app="Kitty"))
    assert result is not None
    assert "kitty @" in result
    assert "--type=tab" in result


def test_build_execute_command_unsupported_terminal() -> None:
    result = build_execute_command("agent-x", _config(terminal_app="Hyper"))
    assert result is None


# --- send_desktop_notification dispatch ---


def test_send_desktop_notification_dispatches_to_macos(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("imbue.mng_notifications.notifier.platform.system", lambda: "Darwin")
    calls: list[tuple[str, str, str | None]] = []
    monkeypatch.setattr(
        "imbue.mng_notifications.notifier._send_macos_notification",
        lambda t, m, e: calls.append((t, m, e)),
    )

    send_desktop_notification("Title", "Message", "agent-x", _config())

    assert len(calls) == 1
    assert calls[0][0] == "Title"


def test_send_desktop_notification_dispatches_to_linux(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("imbue.mng_notifications.notifier.platform.system", lambda: "Linux")
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "imbue.mng_notifications.notifier._send_linux_notification",
        lambda t, m: calls.append((t, m)),
    )

    send_desktop_notification("Title", "Message", "agent-x", _config())

    assert len(calls) == 1


def test_send_desktop_notification_unsupported_platform(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("imbue.mng_notifications.notifier.platform.system", lambda: "Windows")
    send_desktop_notification("Title", "Message", "agent-x", _config())


# --- macOS terminal-notifier ---


def test_send_macos_notification_calls_terminal_notifier(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], **kwargs: Any) -> None:
        calls.append(cmd)

    monkeypatch.setattr("imbue.mng_notifications.notifier.subprocess.run", fake_run)

    _send_macos_notification("Title", "Message", None)

    assert len(calls) == 1
    assert calls[0][0] == "terminal-notifier"
    assert "-title" in calls[0]
    assert "-execute" not in calls[0]


def test_send_macos_notification_with_execute_command(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], **kwargs: Any) -> None:
        calls.append(cmd)

    monkeypatch.setattr("imbue.mng_notifications.notifier.subprocess.run", fake_run)

    _send_macos_notification("Title", "Message", "some-command")

    assert len(calls) == 1
    assert "-execute" in calls[0]
    idx = calls[0].index("-execute")
    assert calls[0][idx + 1] == "some-command"


def test_send_macos_notification_handles_missing_terminal_notifier(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(cmd: list[str], **kwargs: Any) -> None:
        raise FileNotFoundError("terminal-notifier not found")

    monkeypatch.setattr("imbue.mng_notifications.notifier.subprocess.run", fake_run)
    _send_macos_notification("Title", "Message", None)


def test_send_macos_notification_handles_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(cmd: list[str], **kwargs: Any) -> None:
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=10)

    monkeypatch.setattr("imbue.mng_notifications.notifier.subprocess.run", fake_run)
    _send_macos_notification("Title", "Message", None)


# --- Linux notify-send ---


def test_send_linux_notification_calls_notify_send(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], **kwargs: Any) -> None:
        calls.append(cmd)

    monkeypatch.setattr("imbue.mng_notifications.notifier.subprocess.run", fake_run)

    _send_linux_notification("Title", "Message")

    assert calls == [["notify-send", "Title", "Message"]]


def test_send_linux_notification_handles_missing_notify_send(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(cmd: list[str], **kwargs: Any) -> None:
        raise FileNotFoundError("notify-send not found")

    monkeypatch.setattr("imbue.mng_notifications.notifier.subprocess.run", fake_run)
    _send_linux_notification("Title", "Message")


def test_send_linux_notification_handles_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(cmd: list[str], **kwargs: Any) -> None:
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=10)

    monkeypatch.setattr("imbue.mng_notifications.notifier.subprocess.run", fake_run)
    _send_linux_notification("Title", "Message")
