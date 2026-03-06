import json
from collections.abc import Generator
from pathlib import Path

import pytest

from imbue.concurrency_group.concurrency_group import ConcurrencyGroup
from imbue.mng_notifications.config import NotificationsPluginConfig
from imbue.mng_notifications.mock_notifier_test import RecordingNotifier
from imbue.mng_notifications.watcher import _find_agent_event_files
from imbue.mng_notifications.watcher import _process_events
from imbue.mng_notifications.watcher import _read_new_content


@pytest.fixture()
def notification_cg() -> Generator[ConcurrencyGroup, None, None]:
    with ConcurrencyGroup(name="test-notification") as group:
        yield group


def _make_transition_event(
    agent_name: str = "test-agent",
    agent_id: str = "agent-123",
    from_state: str = "RUNNING",
    to_state: str = "WAITING",
) -> str:
    return json.dumps(
        {
            "timestamp": "2026-01-01T00:00:00Z",
            "type": "agent_state_transition",
            "event_id": "evt-abc123",
            "source": "mng_agents",
            "agent_id": agent_id,
            "agent_name": agent_name,
            "from_state": from_state,
            "to_state": to_state,
        }
    )


# --- _find_agent_event_files ---


def test_find_agent_event_files_empty(tmp_path: Path) -> None:
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    assert _find_agent_event_files(agents_dir) == []


def test_find_agent_event_files_finds_events(tmp_path: Path) -> None:
    events_dir = tmp_path / "agents" / "agent-abc" / "events" / "mng_agents"
    events_dir.mkdir(parents=True)
    event_file = events_dir / "events.jsonl"
    event_file.write_text("")
    assert _find_agent_event_files(tmp_path / "agents") == [event_file]


def test_find_agent_event_files_nonexistent_dir(tmp_path: Path) -> None:
    assert _find_agent_event_files(tmp_path / "nonexistent") == []


# --- _read_new_content ---


def test_read_new_content_first_read(tmp_path: Path) -> None:
    event_file = tmp_path / "events.jsonl"
    event_file.write_text("line1\nline2\n")
    tracked: dict[Path, int] = {}

    content = _read_new_content(event_file, tracked)

    assert content == "line1\nline2\n"
    assert tracked[event_file] == event_file.stat().st_size


def test_read_new_content_incremental(tmp_path: Path) -> None:
    event_file = tmp_path / "events.jsonl"
    event_file.write_text("line1\n")
    tracked: dict[Path, int] = {}

    _read_new_content(event_file, tracked)

    with event_file.open("a") as f:
        f.write("line2\n")

    content = _read_new_content(event_file, tracked)
    assert content == "line2\n"


def test_read_new_content_no_change(tmp_path: Path) -> None:
    event_file = tmp_path / "events.jsonl"
    event_file.write_text("line1\n")
    tracked: dict[Path, int] = {}

    _read_new_content(event_file, tracked)
    content = _read_new_content(event_file, tracked)

    assert content == ""


def test_read_new_content_missing_file(tmp_path: Path) -> None:
    tracked: dict[Path, int] = {}
    content = _read_new_content(tmp_path / "nonexistent.jsonl", tracked)
    assert content == ""


# --- _process_events ---


def test_process_events_running_to_waiting(notification_cg: ConcurrencyGroup) -> None:
    notifier = RecordingNotifier()
    content = _make_transition_event(agent_name="my-agent", from_state="RUNNING", to_state="WAITING")

    _process_events(content, NotificationsPluginConfig(), notifier, notification_cg)

    assert len(notifier.calls) == 1
    assert notifier.calls[0][0] == "Agent waiting"
    assert "my-agent" in notifier.calls[0][1]


def test_process_events_waiting_to_running_ignored(notification_cg: ConcurrencyGroup) -> None:
    notifier = RecordingNotifier()
    content = _make_transition_event(from_state="WAITING", to_state="RUNNING")

    _process_events(content, NotificationsPluginConfig(), notifier, notification_cg)

    assert len(notifier.calls) == 0


def test_process_events_non_transition_event_ignored(notification_cg: ConcurrencyGroup) -> None:
    notifier = RecordingNotifier()
    content = json.dumps({"type": "some_other_event", "data": "irrelevant"})

    _process_events(content, NotificationsPluginConfig(), notifier, notification_cg)

    assert len(notifier.calls) == 0


def test_process_events_malformed_json_ignored(notification_cg: ConcurrencyGroup) -> None:
    notifier = RecordingNotifier()

    _process_events("not valid json\n", NotificationsPluginConfig(), notifier, notification_cg)

    assert len(notifier.calls) == 0


def test_process_events_multiple_lines(notification_cg: ConcurrencyGroup) -> None:
    notifier = RecordingNotifier()
    lines = "\n".join(
        [
            _make_transition_event(agent_name="agent-a", from_state="RUNNING", to_state="WAITING"),
            _make_transition_event(agent_name="agent-b", from_state="WAITING", to_state="RUNNING"),
            _make_transition_event(agent_name="agent-c", from_state="RUNNING", to_state="WAITING"),
        ]
    )

    _process_events(lines, NotificationsPluginConfig(), notifier, notification_cg)

    assert len(notifier.calls) == 2
    assert "agent-a" in notifier.calls[0][1]
    assert "agent-c" in notifier.calls[1][1]
