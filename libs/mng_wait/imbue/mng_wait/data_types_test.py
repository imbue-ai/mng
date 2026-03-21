import pytest

from imbue.mng.errors import UserInputError
from imbue.mng.primitives import AgentLifecycleState
from imbue.mng.primitives import HostState
from imbue.mng_wait.data_types import StateSnapshot
from imbue.mng_wait.data_types import check_state_match
from imbue.mng_wait.data_types import compute_default_target_states
from imbue.mng_wait.data_types import validate_state_strings
from imbue.mng_wait.primitives import ALL_VALID_STATE_STRINGS
from imbue.mng_wait.primitives import WaitTargetType

# === compute_default_target_states ===


def test_default_agent_states_include_agent_terminal_states() -> None:
    states = compute_default_target_states(WaitTargetType.AGENT)
    assert "STOPPED" in states
    assert "WAITING" in states
    assert "REPLACED" in states
    assert "DONE" in states


def test_default_agent_states_include_host_terminal_states() -> None:
    states = compute_default_target_states(WaitTargetType.AGENT)
    assert "CRASHED" in states
    assert "FAILED" in states
    assert "DESTROYED" in states
    assert "UNAUTHENTICATED" in states
    assert "PAUSED" in states


def test_default_agent_states_exclude_running() -> None:
    states = compute_default_target_states(WaitTargetType.AGENT)
    assert "RUNNING" not in states


def test_default_host_states_include_terminal_states() -> None:
    states = compute_default_target_states(WaitTargetType.HOST)
    assert "STOPPED" in states
    assert "CRASHED" in states
    assert "FAILED" in states
    assert "DESTROYED" in states
    assert "UNAUTHENTICATED" in states
    assert "PAUSED" in states


def test_default_host_states_exclude_running_and_transient() -> None:
    states = compute_default_target_states(WaitTargetType.HOST)
    assert "RUNNING" not in states
    assert "BUILDING" not in states
    assert "STARTING" not in states
    assert "STOPPING" not in states


# === check_state_match for HOST targets ===


def test_host_target_matches_host_state() -> None:
    snapshot = StateSnapshot(host_state=HostState.STOPPED)
    result = check_state_match(snapshot, WaitTargetType.HOST, frozenset({"STOPPED"}))
    assert result == "STOPPED"


def test_host_target_does_not_match_wrong_state() -> None:
    snapshot = StateSnapshot(host_state=HostState.RUNNING)
    result = check_state_match(snapshot, WaitTargetType.HOST, frozenset({"STOPPED"}))
    assert result is None


def test_host_target_none_host_state_does_not_match() -> None:
    snapshot = StateSnapshot(host_state=None)
    result = check_state_match(snapshot, WaitTargetType.HOST, frozenset({"STOPPED"}))
    assert result is None


# === check_state_match for AGENT targets ===


def test_agent_target_matches_agent_done_state() -> None:
    snapshot = StateSnapshot(
        host_state=HostState.RUNNING,
        agent_state=AgentLifecycleState.DONE,
    )
    result = check_state_match(snapshot, WaitTargetType.AGENT, frozenset({"DONE"}))
    assert result == "DONE"


def test_agent_target_matches_agent_waiting_state() -> None:
    snapshot = StateSnapshot(
        host_state=HostState.RUNNING,
        agent_state=AgentLifecycleState.WAITING,
    )
    result = check_state_match(snapshot, WaitTargetType.AGENT, frozenset({"WAITING"}))
    assert result == "WAITING"


def test_agent_target_running_only_counts_for_agent_not_host() -> None:
    # Agent is STOPPED but host is RUNNING -- should NOT match RUNNING
    snapshot = StateSnapshot(
        host_state=HostState.RUNNING,
        agent_state=AgentLifecycleState.STOPPED,
    )
    result = check_state_match(snapshot, WaitTargetType.AGENT, frozenset({"RUNNING"}))
    assert result is None


def test_agent_target_running_matches_when_agent_is_running() -> None:
    snapshot = StateSnapshot(
        host_state=HostState.RUNNING,
        agent_state=AgentLifecycleState.RUNNING,
    )
    result = check_state_match(snapshot, WaitTargetType.AGENT, frozenset({"RUNNING"}))
    assert result == "RUNNING"


def test_agent_target_stopped_matches_when_agent_stopped() -> None:
    snapshot = StateSnapshot(
        host_state=HostState.RUNNING,
        agent_state=AgentLifecycleState.STOPPED,
    )
    result = check_state_match(snapshot, WaitTargetType.AGENT, frozenset({"STOPPED"}))
    assert result == "STOPPED"


def test_agent_target_stopped_matches_when_host_stopped() -> None:
    snapshot = StateSnapshot(
        host_state=HostState.STOPPED,
        agent_state=AgentLifecycleState.RUNNING,
    )
    result = check_state_match(snapshot, WaitTargetType.AGENT, frozenset({"STOPPED"}))
    assert result == "STOPPED"


def test_agent_target_matches_host_crashed() -> None:
    snapshot = StateSnapshot(
        host_state=HostState.CRASHED,
        agent_state=AgentLifecycleState.RUNNING,
    )
    result = check_state_match(snapshot, WaitTargetType.AGENT, frozenset({"CRASHED"}))
    assert result == "CRASHED"


def test_agent_target_matches_host_paused() -> None:
    snapshot = StateSnapshot(
        host_state=HostState.PAUSED,
        agent_state=AgentLifecycleState.RUNNING,
    )
    result = check_state_match(snapshot, WaitTargetType.AGENT, frozenset({"PAUSED"}))
    assert result == "PAUSED"


def test_agent_target_host_running_does_not_match_when_watching_agent() -> None:
    # When watching an agent and target states include RUNNING,
    # host RUNNING should NOT count -- only agent RUNNING
    snapshot = StateSnapshot(
        host_state=HostState.RUNNING,
        agent_state=AgentLifecycleState.WAITING,
    )
    result = check_state_match(snapshot, WaitTargetType.AGENT, frozenset({"RUNNING"}))
    assert result is None


def test_agent_target_no_match_returns_none() -> None:
    snapshot = StateSnapshot(
        host_state=HostState.RUNNING,
        agent_state=AgentLifecycleState.RUNNING,
    )
    result = check_state_match(snapshot, WaitTargetType.AGENT, frozenset({"DONE", "WAITING"}))
    assert result is None


# === validate_state_strings ===


def test_validate_state_strings_accepts_valid_states() -> None:
    result = validate_state_strings(["STOPPED", "running", "Done"], ALL_VALID_STATE_STRINGS)
    assert result == frozenset({"STOPPED", "RUNNING", "DONE"})


def test_validate_state_strings_rejects_invalid_state() -> None:
    with pytest.raises(UserInputError, match="Invalid state"):
        validate_state_strings(["NONEXISTENT"], ALL_VALID_STATE_STRINGS)


def test_validate_state_strings_empty_input() -> None:
    result = validate_state_strings([], ALL_VALID_STATE_STRINGS)
    assert result == frozenset()
