"""Unit tests for the notification module."""

import subprocess

import pytest

from imbue.mng_notifications.notifier import _escape_applescript_string
from imbue.mng_notifications.notifier import _send_linux_notification
from imbue.mng_notifications.notifier import _send_macos_notification
from imbue.mng_notifications.notifier import send_desktop_notification


def test_escape_applescript_string_plain() -> None:
    """Plain string passes through unchanged."""
    assert _escape_applescript_string("hello world") == "hello world"


def test_escape_applescript_string_double_quotes() -> None:
    """Double quotes are escaped."""
    assert _escape_applescript_string('say "hi"') == 'say \\"hi\\"'


def test_escape_applescript_string_backslash() -> None:
    """Backslashes are escaped before quotes."""
    assert _escape_applescript_string("a\\b") == "a\\\\b"


def test_escape_applescript_string_both() -> None:
    """Backslash followed by quote is properly double-escaped."""
    assert _escape_applescript_string('a\\"b') == 'a\\\\\\"b'


def test_send_desktop_notification_dispatches_to_macos(monkeypatch: pytest.MonkeyPatch) -> None:
    """On Darwin, send_desktop_notification calls _send_macos_notification."""
    monkeypatch.setattr("imbue.mng_notifications.notifier.platform.system", lambda: "Darwin")
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "imbue.mng_notifications.notifier._send_macos_notification",
        lambda t, m: calls.append((t, m)),
    )

    send_desktop_notification("Title", "Message")

    assert calls == [("Title", "Message")]


def test_send_desktop_notification_dispatches_to_linux(monkeypatch: pytest.MonkeyPatch) -> None:
    """On Linux, send_desktop_notification calls _send_linux_notification."""
    monkeypatch.setattr("imbue.mng_notifications.notifier.platform.system", lambda: "Linux")
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "imbue.mng_notifications.notifier._send_linux_notification",
        lambda t, m: calls.append((t, m)),
    )

    send_desktop_notification("Title", "Message")

    assert calls == [("Title", "Message")]


def test_send_desktop_notification_unsupported_platform(monkeypatch: pytest.MonkeyPatch) -> None:
    """On unsupported platforms, a warning is logged (no crash)."""
    monkeypatch.setattr("imbue.mng_notifications.notifier.platform.system", lambda: "Windows")

    # Should not raise
    send_desktop_notification("Title", "Message")


def test_send_macos_notification_calls_osascript(monkeypatch: pytest.MonkeyPatch) -> None:
    """_send_macos_notification calls osascript with the correct script."""
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], **kwargs: object) -> None:
        calls.append(cmd)

    monkeypatch.setattr("imbue.mng_notifications.notifier.subprocess.run", fake_run)

    _send_macos_notification("Test Title", "Test message")

    assert len(calls) == 1
    assert calls[0][0] == "osascript"
    assert calls[0][1] == "-e"
    assert "Test Title" in calls[0][2]
    assert "Test message" in calls[0][2]


def test_send_macos_notification_handles_missing_osascript(monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing osascript logs a warning rather than crashing."""

    def fake_run(cmd: list[str], **kwargs: object) -> None:
        raise FileNotFoundError("osascript not found")

    monkeypatch.setattr("imbue.mng_notifications.notifier.subprocess.run", fake_run)

    # Should not raise
    _send_macos_notification("Title", "Message")


def test_send_macos_notification_handles_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """Timeout during osascript is handled gracefully."""

    def fake_run(cmd: list[str], **kwargs: object) -> None:
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=10)

    monkeypatch.setattr("imbue.mng_notifications.notifier.subprocess.run", fake_run)

    _send_macos_notification("Title", "Message")


def test_send_linux_notification_calls_notify_send(monkeypatch: pytest.MonkeyPatch) -> None:
    """_send_linux_notification calls notify-send with title and message."""
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], **kwargs: object) -> None:
        calls.append(cmd)

    monkeypatch.setattr("imbue.mng_notifications.notifier.subprocess.run", fake_run)

    _send_linux_notification("Test Title", "Test message")

    assert len(calls) == 1
    assert calls[0] == ["notify-send", "Test Title", "Test message"]


def test_send_linux_notification_handles_missing_notify_send(monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing notify-send logs a warning rather than crashing."""

    def fake_run(cmd: list[str], **kwargs: object) -> None:
        raise FileNotFoundError("notify-send not found")

    monkeypatch.setattr("imbue.mng_notifications.notifier.subprocess.run", fake_run)

    _send_linux_notification("Title", "Message")


def test_send_linux_notification_handles_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """Timeout during notify-send is handled gracefully."""

    def fake_run(cmd: list[str], **kwargs: object) -> None:
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=10)

    monkeypatch.setattr("imbue.mng_notifications.notifier.subprocess.run", fake_run)

    _send_linux_notification("Title", "Message")
