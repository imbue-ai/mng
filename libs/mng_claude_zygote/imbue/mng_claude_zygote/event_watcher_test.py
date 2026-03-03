"""Unit tests for event_watcher.py."""

import json
import subprocess
import time
import types
from pathlib import Path
from typing import Any

import pytest

from imbue.mng_claude_zygote.conftest import write_changelings_settings_toml
from imbue.mng_claude_zygote.resources import event_watcher as event_watcher_module
from imbue.mng_claude_zygote.resources.event_watcher import _DeliveryState
from imbue.mng_claude_zygote.resources.event_watcher import _EventWatcherSettings
from imbue.mng_claude_zygote.resources.event_watcher import _SendRateTracker
from imbue.mng_claude_zygote.resources.event_watcher import _TokenBucket
from imbue.mng_claude_zygote.resources.event_watcher import _format_delivery_message
from imbue.mng_claude_zygote.resources.event_watcher import _format_time_since_last
from imbue.mng_claude_zygote.resources.event_watcher import _load_delivery_state
from imbue.mng_claude_zygote.resources.event_watcher import _load_watcher_settings
from imbue.mng_claude_zygote.resources.event_watcher import _save_delivery_state
from imbue.mng_claude_zygote.resources.event_watcher import _send_message
from imbue.mng_claude_zygote.resources.event_watcher import _should_skip_for_catchup


class _SubprocessCapture:
    """Records calls to subprocess.run for assertion in tests."""

    def __init__(self, *, returncode: int = 0, stderr: str = "") -> None:
        self.calls: list[tuple[list[str], dict[str, Any]]] = []
        self._returncode = returncode
        self._stderr = stderr

    def run(self, cmd: list[str], **kwargs: Any) -> types.SimpleNamespace:
        self.calls.append((cmd, kwargs))
        return types.SimpleNamespace(returncode=self._returncode, stdout="", stderr=self._stderr)


@pytest.fixture()
def mock_subprocess_success(monkeypatch: pytest.MonkeyPatch) -> _SubprocessCapture:
    """Replace event_watcher's subprocess with a recording stub (returncode=0)."""
    capture = _SubprocessCapture(returncode=0)
    mock_sp = types.SimpleNamespace(run=capture.run, TimeoutExpired=subprocess.TimeoutExpired)
    monkeypatch.setattr(event_watcher_module, "subprocess", mock_sp)
    return capture


@pytest.fixture()
def mock_subprocess_failure(monkeypatch: pytest.MonkeyPatch) -> _SubprocessCapture:
    """Replace event_watcher's subprocess with a recording stub (returncode=1)."""
    capture = _SubprocessCapture(returncode=1, stderr="send failed")
    mock_sp = types.SimpleNamespace(run=capture.run, TimeoutExpired=subprocess.TimeoutExpired)
    monkeypatch.setattr(event_watcher_module, "subprocess", mock_sp)
    return capture


# -- _load_watcher_settings tests --


def test_load_settings_defaults_when_no_file(tmp_path: Path) -> None:
    settings = _load_watcher_settings(tmp_path)
    assert settings.cel_filter == _EventWatcherSettings().cel_filter
    assert settings.burst_size == 5
    assert settings.max_messages_per_minute == 10
    assert settings.high_rate_warning_threshold == 8


def test_load_settings_reads_custom_values(tmp_path: Path) -> None:
    write_changelings_settings_toml(
        tmp_path,
        "[watchers]\n"
        'event_cel_filter = "source == \\"messages\\""\n'
        "event_burst_size = 3\n"
        "max_event_messages_per_minute = 20\n"
        "high_rate_warning_threshold_per_minute = 15\n",
    )
    settings = _load_watcher_settings(tmp_path)
    assert settings.cel_filter == 'source == "messages"'
    assert settings.burst_size == 3
    assert settings.max_messages_per_minute == 20
    assert settings.high_rate_warning_threshold == 15


def test_load_settings_handles_partial_config(tmp_path: Path) -> None:
    write_changelings_settings_toml(tmp_path, "[watchers]\nevent_burst_size = 7\n")
    settings = _load_watcher_settings(tmp_path)
    assert settings.burst_size == 7
    assert settings.max_messages_per_minute == 10
    assert settings.cel_filter == _EventWatcherSettings().cel_filter


def test_load_settings_handles_corrupt_file(tmp_path: Path) -> None:
    write_changelings_settings_toml(tmp_path, "this is not valid toml {{{")
    settings = _load_watcher_settings(tmp_path)
    assert settings.burst_size == 5


# -- _DeliveryState persistence tests --


def test_load_delivery_state_returns_defaults_when_missing(tmp_path: Path) -> None:
    state = _load_delivery_state(tmp_path / "nonexistent.json")
    assert state.last_event_id == ""
    assert state.last_timestamp == ""


def test_load_delivery_state_reads_valid_file(tmp_path: Path) -> None:
    state_file = tmp_path / "state.json"
    state_file.write_text(json.dumps({"last_event_id": "evt-123", "last_timestamp": "2026-01-01T00:00:00Z"}))
    state = _load_delivery_state(state_file)
    assert state.last_event_id == "evt-123"
    assert state.last_timestamp == "2026-01-01T00:00:00Z"


def test_load_delivery_state_returns_defaults_on_corrupt_json(tmp_path: Path) -> None:
    state_file = tmp_path / "state.json"
    state_file.write_text("not valid json {{{")
    state = _load_delivery_state(state_file)
    assert state.last_event_id == ""
    assert state.last_timestamp == ""


def test_save_and_load_delivery_state_roundtrip(tmp_path: Path) -> None:
    state_file = tmp_path / "state.json"
    original = _DeliveryState(last_event_id="evt-abc", last_timestamp="2026-03-01T12:00:00Z")
    _save_delivery_state(state_file, original)
    loaded = _load_delivery_state(state_file)
    assert loaded.last_event_id == "evt-abc"
    assert loaded.last_timestamp == "2026-03-01T12:00:00Z"


def test_save_delivery_state_creates_parent_directories(tmp_path: Path) -> None:
    state_file = tmp_path / "nested" / "dir" / "state.json"
    state = _DeliveryState(last_event_id="evt-1", last_timestamp="2026-01-01T00:00:00Z")
    _save_delivery_state(state_file, state)
    assert state_file.exists()


# -- _TokenBucket tests --


def test_token_bucket_allows_burst(monkeypatch: pytest.MonkeyPatch) -> None:
    bucket = _TokenBucket(burst_size=3, rate_per_second=0.0)
    assert bucket.consume() is True
    assert bucket.consume() is True
    assert bucket.consume() is True
    assert bucket.consume() is False


def test_token_bucket_refills_over_time(monkeypatch: pytest.MonkeyPatch) -> None:
    # Use a very high rate so refill is immediate after any delay
    bucket = _TokenBucket(burst_size=1, rate_per_second=100.0)
    assert bucket.consume() is True
    assert bucket.consume() is False
    # After a tiny sleep, should have refilled
    time.sleep(0.02)
    assert bucket.consume() is True


def test_token_bucket_time_until_token_when_empty() -> None:
    bucket = _TokenBucket(burst_size=1, rate_per_second=10.0)
    bucket.consume()
    wait = bucket.time_until_token()
    assert wait > 0
    assert wait <= 0.15


def test_token_bucket_time_until_token_when_available() -> None:
    bucket = _TokenBucket(burst_size=3, rate_per_second=1.0)
    assert bucket.time_until_token() == 0.0


def test_token_bucket_does_not_exceed_burst_size() -> None:
    bucket = _TokenBucket(burst_size=2, rate_per_second=1000.0)
    time.sleep(0.01)
    # Even after time passes, should not exceed burst_size
    assert bucket.consume() is True
    assert bucket.consume() is True
    assert bucket.consume() is False


# -- _SendRateTracker tests --


def test_send_rate_tracker_initially_zero() -> None:
    tracker = _SendRateTracker()
    assert tracker.messages_per_minute() == 0.0


def test_send_rate_tracker_counts_sends() -> None:
    tracker = _SendRateTracker()
    tracker.record_send()
    tracker.record_send()
    tracker.record_send()
    assert tracker.messages_per_minute() == 3.0


def test_send_rate_tracker_prunes_old_entries(monkeypatch: pytest.MonkeyPatch) -> None:
    tracker = _SendRateTracker()

    # Record a send "in the past" by manipulating the internal list
    old_time = time.monotonic() - 120.0
    tracker._send_times.append(old_time)

    # Record a recent send
    tracker.record_send()

    # The old entry should be pruned
    assert tracker.messages_per_minute() == 1.0


# -- _should_skip_for_catchup tests --


def test_skip_catchup_returns_false_when_no_prior_state() -> None:
    state = _DeliveryState()
    assert _should_skip_for_catchup({"event_id": "evt-1", "timestamp": "2026-01-01T00:00:00Z"}, state) is False


def test_skip_catchup_returns_true_on_event_id_match() -> None:
    state = _DeliveryState(last_event_id="evt-match", last_timestamp="2026-01-01T00:00:00Z")
    assert _should_skip_for_catchup({"event_id": "evt-match", "timestamp": "2026-01-01T00:00:00Z"}, state) is True


def test_skip_catchup_returns_true_when_timestamp_before_last() -> None:
    state = _DeliveryState(last_event_id="evt-old", last_timestamp="2026-01-02T00:00:00Z")
    assert _should_skip_for_catchup({"event_id": "evt-other", "timestamp": "2026-01-01T00:00:00Z"}, state) is True


def test_skip_catchup_returns_true_when_timestamp_equals_last() -> None:
    state = _DeliveryState(last_event_id="evt-old", last_timestamp="2026-01-01T00:00:00Z")
    assert _should_skip_for_catchup({"event_id": "evt-other", "timestamp": "2026-01-01T00:00:00Z"}, state) is True


def test_skip_catchup_returns_false_when_timestamp_after_last() -> None:
    state = _DeliveryState(last_event_id="evt-old", last_timestamp="2026-01-01T00:00:00Z")
    assert _should_skip_for_catchup({"event_id": "evt-new", "timestamp": "2026-01-02T00:00:00Z"}, state) is False


# -- _format_time_since_last tests --


def test_format_time_seconds() -> None:
    assert _format_time_since_last(30.0) == "30s"


def test_format_time_minutes() -> None:
    assert _format_time_since_last(120.0) == "2.0m"


def test_format_time_hours() -> None:
    assert _format_time_since_last(7200.0) == "2.0h"


# -- _format_delivery_message tests --


def test_format_delivery_message_basic() -> None:
    result = _format_delivery_message(
        event_lines=['{"event": 1}', '{"event": 2}'],
        time_since_last_message_seconds=None,
        rate_warning=None,
    )
    assert "[Event watcher] 2 new event(s)" in result
    assert '{"event": 1}' in result
    assert '{"event": 2}' in result


def test_format_delivery_message_with_time_since_last() -> None:
    result = _format_delivery_message(
        event_lines=['{"event": 1}'],
        time_since_last_message_seconds=45.0,
        rate_warning=None,
    )
    assert "Time since last message: 45s" in result


def test_format_delivery_message_with_time_since_last_minutes() -> None:
    result = _format_delivery_message(
        event_lines=['{"event": 1}'],
        time_since_last_message_seconds=180.0,
        rate_warning=None,
    )
    assert "Time since last message: 3.0m" in result


def test_format_delivery_message_with_rate_warning() -> None:
    result = _format_delivery_message(
        event_lines=['{"event": 1}'],
        time_since_last_message_seconds=None,
        rate_warning="High event rate: 15 messages/min (threshold: 8/min)",
    )
    assert "WARNING:" in result
    assert "High event rate" in result


# -- _send_message tests --


def test_send_message_returns_true_on_success(mock_subprocess_success: _SubprocessCapture) -> None:
    assert _send_message("my-agent", "hello") is True
    assert len(mock_subprocess_success.calls) == 1
    cmd = mock_subprocess_success.calls[0][0]
    assert "mng" in cmd
    assert "message" in cmd
    assert "my-agent" in cmd


def test_send_message_returns_false_on_failure(mock_subprocess_failure: _SubprocessCapture) -> None:
    assert _send_message("my-agent", "hello") is False


def test_send_message_returns_false_on_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    def timeout_run(cmd: list[str], **kwargs: Any) -> types.SimpleNamespace:
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=120)

    mock_sp = types.SimpleNamespace(run=timeout_run, TimeoutExpired=subprocess.TimeoutExpired)
    monkeypatch.setattr(event_watcher_module, "subprocess", mock_sp)
    assert _send_message("my-agent", "hello") is False


def test_send_message_returns_false_on_os_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def os_error_run(cmd: list[str], **kwargs: Any) -> types.SimpleNamespace:
        raise OSError("subprocess launch failed")

    mock_sp = types.SimpleNamespace(run=os_error_run, TimeoutExpired=subprocess.TimeoutExpired)
    monkeypatch.setattr(event_watcher_module, "subprocess", mock_sp)
    assert _send_message("my-agent", "hello") is False
