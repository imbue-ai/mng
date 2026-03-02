"""Unit tests for event_watcher.py."""

import subprocess
import types
from pathlib import Path
from unittest.mock import patch

import pytest

from imbue.mng_claude_zygote.resources.event_watcher import _WatcherSettings
from imbue.mng_claude_zygote.resources.event_watcher import _check_all_sources
from imbue.mng_claude_zygote.resources.event_watcher import _check_and_send_new_events
from imbue.mng_claude_zygote.resources.event_watcher import _get_offset
from imbue.mng_claude_zygote.resources.event_watcher import _load_watcher_settings
from imbue.mng_claude_zygote.resources.event_watcher import _set_offset
from imbue.mng_claude_zygote.resources.watcher_common import Logger

# Patch target for subprocess.run inside the event_watcher module.
# Using patch() with a string target (rather than monkeypatch.setattr on the
# module object) avoids contaminating the global subprocess module, which would
# break unrelated code like the conftest tmux teardown.
_SUBPROCESS_RUN = "imbue.mng_claude_zygote.resources.event_watcher.subprocess.run"


# -- _WatcherSettings tests --


def test_watcher_settings_defaults() -> None:
    settings = _WatcherSettings()
    assert settings.poll_interval == 3
    assert settings.sources == ["messages", "scheduled", "mng_agents", "stop"]


def test_watcher_settings_is_frozen() -> None:
    settings = _WatcherSettings()
    with pytest.raises(AttributeError):
        settings.poll_interval = 10  # type: ignore[misc]


# -- _load_watcher_settings tests --


def test_load_settings_defaults_when_no_file(tmp_path: Path) -> None:
    settings = _load_watcher_settings(tmp_path)
    assert settings.poll_interval == 3
    assert settings.sources == ["messages", "scheduled", "mng_agents", "stop"]


def test_load_settings_reads_from_file(tmp_path: Path) -> None:
    (tmp_path / "settings.toml").write_text(
        '[watchers]\nevent_poll_interval_seconds = 10\nwatched_event_sources = ["messages", "stop"]\n'
    )
    settings = _load_watcher_settings(tmp_path)
    assert settings.poll_interval == 10
    assert settings.sources == ["messages", "stop"]


def test_load_settings_handles_corrupt_file(tmp_path: Path) -> None:
    (tmp_path / "settings.toml").write_text("this is not valid toml {{{")
    settings = _load_watcher_settings(tmp_path)
    assert settings.poll_interval == 3


def test_load_settings_handles_partial_config(tmp_path: Path) -> None:
    (tmp_path / "settings.toml").write_text("[watchers]\nevent_poll_interval_seconds = 7\n")
    settings = _load_watcher_settings(tmp_path)
    assert settings.poll_interval == 7
    assert settings.sources == ["messages", "scheduled", "mng_agents", "stop"]


# -- _get_offset / _set_offset tests --


def test_get_offset_returns_zero_when_missing(tmp_path: Path) -> None:
    offsets_dir = tmp_path / "offsets"
    offsets_dir.mkdir()
    assert _get_offset(offsets_dir, "messages") == 0


def test_set_and_get_offset_roundtrip(tmp_path: Path) -> None:
    offsets_dir = tmp_path / "offsets"
    offsets_dir.mkdir()
    _set_offset(offsets_dir, "messages", 42)
    assert _get_offset(offsets_dir, "messages") == 42


def test_get_offset_returns_zero_for_corrupt_file(tmp_path: Path) -> None:
    offsets_dir = tmp_path / "offsets"
    offsets_dir.mkdir()
    (offsets_dir / "messages.offset").write_text("not_a_number")
    assert _get_offset(offsets_dir, "messages") == 0


def test_set_offset_overwrites_previous(tmp_path: Path) -> None:
    offsets_dir = tmp_path / "offsets"
    offsets_dir.mkdir()
    _set_offset(offsets_dir, "messages", 10)
    _set_offset(offsets_dir, "messages", 20)
    assert _get_offset(offsets_dir, "messages") == 20


# -- _check_and_send_new_events tests --


def test_check_and_send_does_nothing_when_no_events_file(tmp_path: Path) -> None:
    """No crash when events file does not exist."""
    offsets_dir = tmp_path / "offsets"
    offsets_dir.mkdir()
    events_file = tmp_path / "events.jsonl"
    log = Logger(tmp_path / "test.log")

    with patch(_SUBPROCESS_RUN) as mock_run:
        _check_and_send_new_events(events_file, "test_source", offsets_dir, "agent", log)
        mock_run.assert_not_called()


def test_check_and_send_does_nothing_when_at_current_offset(tmp_path: Path) -> None:
    offsets_dir = tmp_path / "offsets"
    offsets_dir.mkdir()
    events_file = tmp_path / "events.jsonl"
    events_file.write_text('{"event": 1}\n')
    _set_offset(offsets_dir, "test_source", 1)
    log = Logger(tmp_path / "test.log")

    with patch(_SUBPROCESS_RUN) as mock_run:
        _check_and_send_new_events(events_file, "test_source", offsets_dir, "agent", log)
        mock_run.assert_not_called()


def test_check_and_send_sends_new_events_and_updates_offset(tmp_path: Path) -> None:
    offsets_dir = tmp_path / "offsets"
    offsets_dir.mkdir()
    events_file = tmp_path / "events.jsonl"
    events_file.write_text('{"event": 1}\n{"event": 2}\n{"event": 3}\n')
    (offsets_dir / "test_source.offset").write_text("1")
    log = Logger(tmp_path / "test.log")

    with patch(_SUBPROCESS_RUN, return_value=types.SimpleNamespace(returncode=0, stdout="", stderr="")) as mock_run:
        _check_and_send_new_events(events_file, "test_source", offsets_dir, "my-agent", log)

        assert mock_run.call_count == 1
        cmd = mock_run.call_args[0][0]
        assert "mng" in cmd and "message" in cmd
        assert "my-agent" in cmd
        assert '{"event": 2}' in cmd[-1]
        assert '{"event": 3}' in cmd[-1]
        assert _get_offset(offsets_dir, "test_source") == 3


def test_check_and_send_does_not_update_offset_on_failure(tmp_path: Path) -> None:
    offsets_dir = tmp_path / "offsets"
    offsets_dir.mkdir()
    events_file = tmp_path / "events.jsonl"
    events_file.write_text('{"event": 1}\n{"event": 2}\n')
    log = Logger(tmp_path / "test.log")

    with patch(_SUBPROCESS_RUN, return_value=types.SimpleNamespace(returncode=1, stdout="", stderr="send failed")):
        _check_and_send_new_events(events_file, "test_source", offsets_dir, "my-agent", log)
        assert _get_offset(offsets_dir, "test_source") == 0


def test_check_and_send_handles_timeout(tmp_path: Path) -> None:
    offsets_dir = tmp_path / "offsets"
    offsets_dir.mkdir()
    events_file = tmp_path / "events.jsonl"
    events_file.write_text('{"event": 1}\n')
    log = Logger(tmp_path / "test.log")

    with patch(_SUBPROCESS_RUN, side_effect=subprocess.TimeoutExpired(cmd=["mng"], timeout=120)):
        _check_and_send_new_events(events_file, "test_source", offsets_dir, "agent", log)
        assert _get_offset(offsets_dir, "test_source") == 0


def test_check_and_send_handles_os_error(tmp_path: Path) -> None:
    offsets_dir = tmp_path / "offsets"
    offsets_dir.mkdir()
    events_file = tmp_path / "events.jsonl"
    events_file.write_text('{"event": 1}\n')
    log = Logger(tmp_path / "test.log")

    with patch(_SUBPROCESS_RUN, side_effect=OSError("subprocess launch failed")):
        _check_and_send_new_events(events_file, "test_source", offsets_dir, "agent", log)
        assert _get_offset(offsets_dir, "test_source") == 0


def test_check_and_send_skips_empty_new_lines(tmp_path: Path) -> None:
    """When new lines are all whitespace, should not send a message."""
    offsets_dir = tmp_path / "offsets"
    offsets_dir.mkdir()
    events_file = tmp_path / "events.jsonl"
    events_file.write_text('{"event": 1}\n\n\n')
    _set_offset(offsets_dir, "test_source", 1)
    log = Logger(tmp_path / "test.log")

    with patch(_SUBPROCESS_RUN) as mock_run:
        _check_and_send_new_events(events_file, "test_source", offsets_dir, "agent", log)
        mock_run.assert_not_called()


# -- _check_all_sources tests --


def test_check_all_sources_iterates_all_sources(tmp_path: Path) -> None:
    logs_dir = tmp_path / "logs"
    offsets_dir = logs_dir / ".event_offsets"
    offsets_dir.mkdir(parents=True)
    log = Logger(tmp_path / "test.log")

    for source in ("messages", "stop"):
        source_dir = logs_dir / source
        source_dir.mkdir(parents=True)
        (source_dir / "events.jsonl").write_text(f'{{"source": "{source}"}}\n')

    with patch(_SUBPROCESS_RUN, return_value=types.SimpleNamespace(returncode=0, stdout="", stderr="")) as mock_run:
        _check_all_sources(logs_dir, ["messages", "stop"], offsets_dir, "agent", log)
        assert mock_run.call_count == 2


def test_check_all_sources_skips_missing_event_files(tmp_path: Path) -> None:
    logs_dir = tmp_path / "logs"
    offsets_dir = logs_dir / ".event_offsets"
    offsets_dir.mkdir(parents=True)
    log = Logger(tmp_path / "test.log")

    with patch(_SUBPROCESS_RUN) as mock_run:
        _check_all_sources(logs_dir, ["nonexistent"], offsets_dir, "agent", log)
        mock_run.assert_not_called()
