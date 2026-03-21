from imbue.mng.primitives import AgentId
from imbue.mng.primitives import AgentLifecycleState
from imbue.mng.primitives import AgentName
from imbue.mng.primitives import DiscoveredAgent
from imbue.mng.primitives import DiscoveredHost
from imbue.mng.primitives import HostId
from imbue.mng.primitives import HostName
from imbue.mng.primitives import HostState
from imbue.mng.primitives import ProviderInstanceName
from imbue.mng_wait.api import _detect_state_changes
from imbue.mng_wait.api import _is_agent_match
from imbue.mng_wait.api import _is_host_match
from imbue.mng_wait.data_types import StateChange
from imbue.mng_wait.data_types import StateSnapshot

# === _is_agent_match ===


def test_is_agent_match_by_valid_id() -> None:
    agent_id = AgentId.generate()
    agent = DiscoveredAgent(
        host_id=HostId.generate(),
        agent_id=agent_id,
        agent_name=AgentName("test-agent"),
        provider_name=ProviderInstanceName("local"),
    )
    assert _is_agent_match(agent, str(agent_id), is_agent_id=True) is True


def test_is_agent_match_by_name() -> None:
    agent = DiscoveredAgent(
        host_id=HostId.generate(),
        agent_id=AgentId.generate(),
        agent_name=AgentName("my-agent"),
        provider_name=ProviderInstanceName("local"),
    )
    assert _is_agent_match(agent, "my-agent", is_agent_id=False) is True


def test_is_agent_match_wrong_name() -> None:
    agent = DiscoveredAgent(
        host_id=HostId.generate(),
        agent_id=AgentId.generate(),
        agent_name=AgentName("other-agent"),
        provider_name=ProviderInstanceName("local"),
    )
    assert _is_agent_match(agent, "my-agent", is_agent_id=False) is False


def test_is_agent_match_invalid_id_format() -> None:
    agent = DiscoveredAgent(
        host_id=HostId.generate(),
        agent_id=AgentId.generate(),
        agent_name=AgentName("test-agent"),
        provider_name=ProviderInstanceName("local"),
    )
    # An invalid ID format should return False, not raise
    assert _is_agent_match(agent, "not-a-valid-id", is_agent_id=True) is False


# === _is_host_match ===


def test_is_host_match_by_valid_id() -> None:
    host_id = HostId.generate()
    host = DiscoveredHost(
        host_id=host_id,
        host_name=HostName("test-host"),
        provider_name=ProviderInstanceName("local"),
    )
    assert _is_host_match(host, str(host_id), is_host_id=True) is True


def test_is_host_match_by_name() -> None:
    host = DiscoveredHost(
        host_id=HostId.generate(),
        host_name=HostName("my-host"),
        provider_name=ProviderInstanceName("local"),
    )
    assert _is_host_match(host, "my-host", is_host_id=False) is True


def test_is_host_match_wrong_name() -> None:
    host = DiscoveredHost(
        host_id=HostId.generate(),
        host_name=HostName("other-host"),
        provider_name=ProviderInstanceName("local"),
    )
    assert _is_host_match(host, "my-host", is_host_id=False) is False


# === _detect_state_changes ===


def test_detect_state_changes_records_host_state_change() -> None:
    previous = StateSnapshot(host_state=HostState.RUNNING)
    current = StateSnapshot(host_state=HostState.STOPPED)
    changes: list[StateChange] = []
    recorded: list[StateChange] = []

    _detect_state_changes(
        previous_snapshot=previous,
        current_snapshot=current,
        elapsed=5.0,
        state_changes=changes,
        on_state_change=recorded.append,
    )

    assert len(changes) == 1
    assert changes[0].field == "host_state"
    assert changes[0].old_value == "RUNNING"
    assert changes[0].new_value == "STOPPED"
    assert len(recorded) == 1


def test_detect_state_changes_records_agent_state_change() -> None:
    previous = StateSnapshot(
        host_state=HostState.RUNNING,
        agent_state=AgentLifecycleState.RUNNING,
    )
    current = StateSnapshot(
        host_state=HostState.RUNNING,
        agent_state=AgentLifecycleState.WAITING,
    )
    changes: list[StateChange] = []

    _detect_state_changes(
        previous_snapshot=previous,
        current_snapshot=current,
        elapsed=10.0,
        state_changes=changes,
        on_state_change=None,
    )

    assert len(changes) == 1
    assert changes[0].field == "agent_state"
    assert changes[0].old_value == "RUNNING"
    assert changes[0].new_value == "WAITING"


def test_detect_state_changes_no_change_records_nothing() -> None:
    snapshot = StateSnapshot(
        host_state=HostState.RUNNING,
        agent_state=AgentLifecycleState.RUNNING,
    )
    changes: list[StateChange] = []

    _detect_state_changes(
        previous_snapshot=snapshot,
        current_snapshot=snapshot,
        elapsed=5.0,
        state_changes=changes,
        on_state_change=None,
    )

    assert len(changes) == 0


def test_detect_state_changes_both_change() -> None:
    previous = StateSnapshot(
        host_state=HostState.RUNNING,
        agent_state=AgentLifecycleState.RUNNING,
    )
    current = StateSnapshot(
        host_state=HostState.STOPPED,
        agent_state=AgentLifecycleState.STOPPED,
    )
    changes: list[StateChange] = []

    _detect_state_changes(
        previous_snapshot=previous,
        current_snapshot=current,
        elapsed=15.0,
        state_changes=changes,
        on_state_change=None,
    )

    assert len(changes) == 2
    assert changes[0].field == "host_state"
    assert changes[1].field == "agent_state"


def test_detect_state_changes_skips_none_previous() -> None:
    previous = StateSnapshot()
    current = StateSnapshot(host_state=HostState.RUNNING)
    changes: list[StateChange] = []

    _detect_state_changes(
        previous_snapshot=previous,
        current_snapshot=current,
        elapsed=1.0,
        state_changes=changes,
        on_state_change=None,
    )

    # No change recorded because previous was None
    assert len(changes) == 0
