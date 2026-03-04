"""Unit tests for the notification module."""

import shlex

import pytest

from imbue.mng_notifications.config import NotificationsPluginConfig
from imbue.mng_notifications.notifier import LinuxNotifier
from imbue.mng_notifications.notifier import MacOSNotifier
from imbue.mng_notifications.notifier import build_execute_command
from imbue.mng_notifications.notifier import get_notifier


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
    """custom_terminal_command is used with MNG_AGENT_NAME_FOR_NOTIFICATIONS_PLUGIN exported for shell expansion."""
    result = build_execute_command(
        "agent-x", _config(custom_terminal_command="my-cmd $MNG_AGENT_NAME_FOR_NOTIFICATIONS_PLUGIN")
    )
    assert result is not None
    assert (
        result
        == "export MNG_AGENT_NAME_FOR_NOTIFICATIONS_PLUGIN=agent-x && my-cmd $MNG_AGENT_NAME_FOR_NOTIFICATIONS_PLUGIN"
    )


def test_build_execute_command_custom_command_with_quotes_in_name() -> None:
    """Agent names with single quotes are properly escaped via shlex.quote."""
    result = build_execute_command("it's-agent", _config(custom_terminal_command="my-cmd"))
    assert result is not None
    expected_name = shlex.quote("it's-agent")
    assert result == f"export MNG_AGENT_NAME_FOR_NOTIFICATIONS_PLUGIN={expected_name} && my-cmd"


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


# --- get_notifier ---


def test_get_notifier_macos(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("imbue.mng_notifications.notifier.platform.system", lambda: "Darwin")
    assert isinstance(get_notifier(), MacOSNotifier)


def test_get_notifier_linux(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("imbue.mng_notifications.notifier.platform.system", lambda: "Linux")
    assert isinstance(get_notifier(), LinuxNotifier)


def test_get_notifier_unsupported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("imbue.mng_notifications.notifier.platform.system", lambda: "Windows")
    assert get_notifier() is None


# --- MacOSNotifier ---


def test_macos_notifier_builds_correct_command(fake_subprocess_run: list[list[str]]) -> None:
    MacOSNotifier().notify("Title", "Message", None)

    assert len(fake_subprocess_run) == 1
    assert fake_subprocess_run[0][0] == "terminal-notifier"
    assert "-title" in fake_subprocess_run[0]
    assert "-execute" not in fake_subprocess_run[0]


def test_macos_notifier_includes_execute_command(fake_subprocess_run: list[list[str]]) -> None:
    MacOSNotifier().notify("Title", "Message", "some-command")

    assert len(fake_subprocess_run) == 1
    assert "-execute" in fake_subprocess_run[0]
    idx = fake_subprocess_run[0].index("-execute")
    assert fake_subprocess_run[0][idx + 1] == "some-command"


# --- LinuxNotifier ---


def test_linux_notifier_calls_notify_send(fake_subprocess_run: list[list[str]]) -> None:
    LinuxNotifier().notify("Title", "Message", None)

    assert fake_subprocess_run == [["notify-send", "Title", "Message"]]


# --- Error handling (missing binaries / timeouts) ---


def test_macos_notifier_handles_missing_binary(fake_subprocess_run_raising: None) -> None:
    MacOSNotifier().notify("Title", "Message", None)


def test_macos_notifier_handles_timeout(fake_subprocess_run_timeout: None) -> None:
    MacOSNotifier().notify("Title", "Message", None)


def test_linux_notifier_handles_missing_binary(fake_subprocess_run_raising: None) -> None:
    LinuxNotifier().notify("Title", "Message", None)


def test_linux_notifier_handles_timeout(fake_subprocess_run_timeout: None) -> None:
    LinuxNotifier().notify("Title", "Message", None)
