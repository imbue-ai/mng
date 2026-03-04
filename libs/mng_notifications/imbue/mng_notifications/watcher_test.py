"""Unit tests for agent state transition detection."""

from collections.abc import Generator
from datetime import datetime
from datetime import timezone
from pathlib import Path

import pytest

from imbue.concurrency_group.concurrency_group import ConcurrencyGroup
from imbue.mng.api.list import ListResult
from imbue.mng.config.data_types import MngContext
from imbue.mng.interfaces.data_types import AgentDetails
from imbue.mng.interfaces.data_types import HostDetails
from imbue.mng.primitives import AgentId
from imbue.mng.primitives import AgentLifecycleState
from imbue.mng.primitives import AgentName
from imbue.mng.primitives import CommandString
from imbue.mng.primitives import HostId
from imbue.mng.primitives import HostState
from imbue.mng.primitives import ProviderInstanceName
from imbue.mng_notifications.config import NotificationsPluginConfig
from imbue.mng_notifications.mock_notifier_test import RecordingNotifier
from imbue.mng_notifications.testing import patch_list_agents_raises_mng_error
from imbue.mng_notifications.testing import patch_list_agents_returns
from imbue.mng_notifications.watcher import _notify_agent_waiting
from imbue.mng_notifications.watcher import _poll_agents
from imbue.mng_notifications.watcher import build_state_map
from imbue.mng_notifications.watcher import detect_waiting_transitions


def _make_host_details() -> HostDetails:
    return HostDetails(
        id=HostId.generate(),
        name="test-host",
        provider_name=ProviderInstanceName("local"),
        state=HostState.RUNNING,
    )


def _make_agent(
    agent_id: AgentId | None = None,
    name: str = "test-agent",
    state: AgentLifecycleState = AgentLifecycleState.RUNNING,
) -> AgentDetails:
    return AgentDetails(
        id=agent_id or AgentId.generate(),
        name=AgentName(name),
        type="claude",
        command=CommandString("claude"),
        work_dir=Path("/tmp/test"),
        create_time=datetime.now(timezone.utc),
        start_on_boot=False,
        state=state,
        labels={},
        host=_make_host_details(),
    )


@pytest.fixture()
def notification_cg() -> Generator[ConcurrencyGroup, None, None]:
    with ConcurrencyGroup(name="test-notification") as group:
        yield group


def test_detect_waiting_transitions_running_to_waiting() -> None:
    """Detect a RUNNING -> WAITING transition."""
    agent_id = AgentId.generate()
    previous = {agent_id: AgentLifecycleState.RUNNING}
    current = [_make_agent(agent_id=agent_id, state=AgentLifecycleState.WAITING)]

    result = detect_waiting_transitions(previous, current)

    assert len(result) == 1
    assert result[0].id == agent_id


def test_detect_waiting_transitions_no_change() -> None:
    """No transitions when state doesn't change."""
    agent_id = AgentId.generate()
    previous = {agent_id: AgentLifecycleState.RUNNING}
    current = [_make_agent(agent_id=agent_id, state=AgentLifecycleState.RUNNING)]

    result = detect_waiting_transitions(previous, current)

    assert len(result) == 0


def test_detect_waiting_transitions_waiting_to_running_ignored() -> None:
    """WAITING -> RUNNING is not a relevant transition."""
    agent_id = AgentId.generate()
    previous = {agent_id: AgentLifecycleState.WAITING}
    current = [_make_agent(agent_id=agent_id, state=AgentLifecycleState.RUNNING)]

    result = detect_waiting_transitions(previous, current)

    assert len(result) == 0


def test_detect_waiting_transitions_stopped_to_waiting_ignored() -> None:
    """STOPPED -> WAITING is not a relevant transition."""
    agent_id = AgentId.generate()
    previous = {agent_id: AgentLifecycleState.STOPPED}
    current = [_make_agent(agent_id=agent_id, state=AgentLifecycleState.WAITING)]

    result = detect_waiting_transitions(previous, current)

    assert len(result) == 0


def test_detect_waiting_transitions_new_agent_ignored() -> None:
    """A new agent (not in previous states) should not trigger a transition."""
    current = [_make_agent(state=AgentLifecycleState.WAITING)]

    result = detect_waiting_transitions({}, current)

    assert len(result) == 0


def test_detect_waiting_transitions_multiple_agents() -> None:
    """Multiple agents, only the one transitioning should be detected."""
    agent_a = AgentId.generate()
    agent_b = AgentId.generate()
    agent_c = AgentId.generate()

    previous = {
        agent_a: AgentLifecycleState.RUNNING,
        agent_b: AgentLifecycleState.RUNNING,
        agent_c: AgentLifecycleState.WAITING,
    }
    current = [
        _make_agent(agent_id=agent_a, name="a", state=AgentLifecycleState.WAITING),
        _make_agent(agent_id=agent_b, name="b", state=AgentLifecycleState.RUNNING),
        _make_agent(agent_id=agent_c, name="c", state=AgentLifecycleState.WAITING),
    ]

    result = detect_waiting_transitions(previous, current)

    assert len(result) == 1
    assert result[0].id == agent_a


def test_build_state_map() -> None:
    """Build a state map from agent details."""
    agent_a = AgentId.generate()
    agent_b = AgentId.generate()
    agents = [
        _make_agent(agent_id=agent_a, state=AgentLifecycleState.RUNNING),
        _make_agent(agent_id=agent_b, state=AgentLifecycleState.WAITING),
    ]

    result = build_state_map(agents)

    assert result == {
        agent_a: AgentLifecycleState.RUNNING,
        agent_b: AgentLifecycleState.WAITING,
    }


def test_build_state_map_empty() -> None:
    """Empty agent list produces empty state map."""
    result = build_state_map([])
    assert result == {}


def test_notify_agent_waiting_sends_notification(notification_cg: ConcurrencyGroup) -> None:
    """_notify_agent_waiting sends a desktop notification with the agent name."""
    notifier = RecordingNotifier()

    agent = _make_agent(name="my-cool-agent", state=AgentLifecycleState.WAITING)
    _notify_agent_waiting(agent, NotificationsPluginConfig(), notifier, notification_cg)

    assert len(notifier.calls) == 1
    assert notifier.calls[0][0] == "Agent waiting"
    assert "my-cool-agent" in notifier.calls[0][1]


def test_poll_agents_returns_agent_list(monkeypatch: pytest.MonkeyPatch, temp_mng_ctx: MngContext) -> None:
    """_poll_agents returns the list of agents from list_agents."""
    agent = _make_agent(name="polled-agent")
    patch_list_agents_returns(monkeypatch, ListResult(agents=[agent]))

    result = _poll_agents(temp_mng_ctx, (), ())

    assert result is not None
    assert len(result) == 1
    assert result[0].name == AgentName("polled-agent")


def test_poll_agents_returns_none_on_mng_error(monkeypatch: pytest.MonkeyPatch, temp_mng_ctx: MngContext) -> None:
    """_poll_agents returns None when list_agents raises MngError."""
    patch_list_agents_raises_mng_error(monkeypatch)

    result = _poll_agents(temp_mng_ctx, (), ())

    assert result is None
