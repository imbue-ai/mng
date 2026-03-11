import json

import pytest

from imbue.mng.api.observe import AgentStateEvent
from imbue.mng.api.observe import FullAgentStateEvent
from imbue.mng.api.observe import OBSERVE_EVENT_SOURCE
from imbue.mng.api.observe import ObserveEventType
from imbue.mng.api.observe import ObserveLockError
from imbue.mng.api.observe import acquire_observe_lock
from imbue.mng.api.observe import agent_state_has_changed
from imbue.mng.api.observe import append_observe_event
from imbue.mng.api.observe import extract_comparable_agent_state
from imbue.mng.api.observe import get_observe_events_dir
from imbue.mng.api.observe import get_observe_events_path
from imbue.mng.api.observe import get_observe_lock_path
from imbue.mng.api.observe import make_agent_state_event
from imbue.mng.api.observe import make_full_agent_state_event
from imbue.mng.api.observe import release_observe_lock
from imbue.mng.config.data_types import MngConfig
from imbue.mng.primitives import AgentLifecycleState
from imbue.mng.utils.testing import make_test_agent_details

# === Path Helper Tests ===


def test_get_observe_events_dir_returns_correct_path(temp_config: MngConfig) -> None:
    events_dir = get_observe_events_dir(temp_config)
    assert events_dir == temp_config.default_host_dir / "events" / "mng" / "agents"


def test_get_observe_events_path_returns_jsonl_file(temp_config: MngConfig) -> None:
    events_path = get_observe_events_path(temp_config)
    assert events_path.name == "events.jsonl"
    assert events_path.parent.name == "agents"


def test_get_observe_lock_path_returns_correct_path(temp_config: MngConfig) -> None:
    lock_path = get_observe_lock_path(temp_config)
    assert lock_path == temp_config.default_host_dir / "observe_lock"


# === Event Construction Tests ===


def test_make_agent_state_event_has_correct_fields() -> None:
    agent = make_test_agent_details()
    event = make_agent_state_event(agent)
    assert event.type == ObserveEventType.AGENT_STATE
    assert event.source == OBSERVE_EVENT_SOURCE
    assert event.event_id.startswith("evt-")
    assert event.agent["name"] == "test-agent"
    assert isinstance(event, AgentStateEvent)


def test_make_full_agent_state_event_has_correct_fields() -> None:
    agents = [make_test_agent_details(name="agent-1"), make_test_agent_details(name="agent-2")]
    event = make_full_agent_state_event(agents)
    assert event.type == ObserveEventType.AGENTS_FULL_STATE
    assert event.source == OBSERVE_EVENT_SOURCE
    assert event.event_id.startswith("evt-")
    assert len(event.agents) == 2
    assert isinstance(event, FullAgentStateEvent)


def test_make_full_agent_state_event_with_empty_agents() -> None:
    event = make_full_agent_state_event([])
    assert event.type == ObserveEventType.AGENTS_FULL_STATE
    assert len(event.agents) == 0


# === File I/O Tests ===


def test_append_observe_event_creates_file_and_writes_valid_json(temp_config: MngConfig) -> None:
    agent = make_test_agent_details()
    event = make_agent_state_event(agent)
    append_observe_event(temp_config, event)

    events_path = get_observe_events_path(temp_config)
    assert events_path.exists()

    lines = events_path.read_text().strip().splitlines()
    assert len(lines) == 1
    data = json.loads(lines[0])
    assert data["type"] == ObserveEventType.AGENT_STATE
    assert data["source"] == "mng/agents"


def test_append_observe_event_appends_multiple_events(temp_config: MngConfig) -> None:
    for idx in range(3):
        agent = make_test_agent_details(name=f"agent-{idx}")
        event = make_agent_state_event(agent)
        append_observe_event(temp_config, event)

    events_path = get_observe_events_path(temp_config)
    lines = events_path.read_text().strip().splitlines()
    assert len(lines) == 3


def test_append_observe_event_creates_parent_directories(temp_config: MngConfig) -> None:
    events_path = get_observe_events_path(temp_config)
    assert not events_path.parent.exists()

    agent = make_test_agent_details()
    event = make_agent_state_event(agent)
    append_observe_event(temp_config, event)
    assert events_path.parent.exists()


# === Comparable State Tests ===


def test_extract_comparable_agent_state_includes_key_fields() -> None:
    agent = make_test_agent_details(name="my-agent", state=AgentLifecycleState.RUNNING)
    comparable = extract_comparable_agent_state(agent)

    assert comparable["name"] == "my-agent"
    assert comparable["state"] == "RUNNING"
    assert "id" in comparable
    assert "host_id" in comparable
    assert "host_state" in comparable
    assert "work_dir" in comparable
    assert "command" in comparable


def test_extract_comparable_agent_state_excludes_volatile_fields() -> None:
    agent = make_test_agent_details()
    comparable = extract_comparable_agent_state(agent)

    assert "idle_seconds" not in comparable
    assert "runtime_seconds" not in comparable
    assert "user_activity_time" not in comparable
    assert "agent_activity_time" not in comparable


def test_agent_state_has_changed_returns_true_for_new_agent() -> None:
    agent = make_test_agent_details()
    last_state: dict[str, str] = {}
    assert agent_state_has_changed(agent, last_state) is True


def test_agent_state_has_changed_returns_false_for_same_state() -> None:
    agent = make_test_agent_details()
    comparable = extract_comparable_agent_state(agent)
    comparable_json = json.dumps(comparable, sort_keys=True)
    last_state = {str(agent.id): comparable_json}
    assert agent_state_has_changed(agent, last_state) is False


def test_agent_state_has_changed_returns_true_for_state_change() -> None:
    agent_running = make_test_agent_details(state=AgentLifecycleState.RUNNING)
    comparable = extract_comparable_agent_state(agent_running)
    comparable_json = json.dumps(comparable, sort_keys=True)
    last_state = {str(agent_running.id): comparable_json}

    # Simulate the same agent transitioning to STOPPED
    agent_stopped = make_test_agent_details(state=AgentLifecycleState.STOPPED)
    assert agent_state_has_changed(agent_stopped, last_state) is True


# === Lock Tests ===


def test_acquire_and_release_observe_lock(temp_config: MngConfig) -> None:
    fd = acquire_observe_lock(temp_config)
    assert fd >= 0
    release_observe_lock(fd)


def test_acquire_observe_lock_fails_when_already_held(temp_config: MngConfig) -> None:
    fd = acquire_observe_lock(temp_config)
    try:
        with pytest.raises(ObserveLockError):
            acquire_observe_lock(temp_config)
    finally:
        release_observe_lock(fd)


def test_acquire_observe_lock_succeeds_after_release(temp_config: MngConfig) -> None:
    fd = acquire_observe_lock(temp_config)
    release_observe_lock(fd)

    fd2 = acquire_observe_lock(temp_config)
    release_observe_lock(fd2)


def test_observe_lock_creates_lock_file(temp_config: MngConfig) -> None:
    lock_path = get_observe_lock_path(temp_config)
    assert not lock_path.exists()

    fd = acquire_observe_lock(temp_config)
    assert lock_path.exists()
    release_observe_lock(fd)


# === Serialization Roundtrip Tests ===


def test_agent_state_event_serializes_to_valid_json() -> None:
    agent = make_test_agent_details()
    event = make_agent_state_event(agent)
    data = event.model_dump(mode="json")
    json_str = json.dumps(data, separators=(",", ":"))

    parsed = json.loads(json_str)
    assert parsed["type"] == "AGENT_STATE"
    assert parsed["source"] == "mng/agents"
    assert "agent" in parsed
    assert parsed["agent"]["name"] == "test-agent"


def test_full_agent_state_event_serializes_to_valid_json() -> None:
    agents = [make_test_agent_details(name="a1"), make_test_agent_details(name="a2")]
    event = make_full_agent_state_event(agents)
    data = event.model_dump(mode="json")
    json_str = json.dumps(data, separators=(",", ":"))

    parsed = json.loads(json_str)
    assert parsed["type"] == "AGENTS_FULL_STATE"
    assert len(parsed["agents"]) == 2
