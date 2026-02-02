"""Unit tests for the create API."""

from unittest.mock import Mock

from imbue.mngr.api.create import _wait_for_agent_ready
from imbue.mngr.primitives import AgentLifecycleState


def test_wait_for_agent_ready_returns_true_when_waiting() -> None:
    """_wait_for_agent_ready should return True when agent reaches WAITING state."""
    mock_agent = Mock()
    mock_agent.name = "test-agent"
    mock_agent.get_lifecycle_state.return_value = AgentLifecycleState.WAITING

    result = _wait_for_agent_ready(mock_agent, timeout_seconds=1.0)

    assert result is True
    mock_agent.get_lifecycle_state.assert_called()


def test_wait_for_agent_ready_returns_false_on_timeout() -> None:
    """_wait_for_agent_ready should return False when timeout expires without WAITING state."""
    mock_agent = Mock()
    mock_agent.name = "test-agent"
    # Always return RUNNING, never WAITING
    mock_agent.get_lifecycle_state.return_value = AgentLifecycleState.RUNNING

    result = _wait_for_agent_ready(mock_agent, timeout_seconds=0.5, poll_interval_seconds=0.1)

    assert result is False
    # Should have been called multiple times during polling
    assert mock_agent.get_lifecycle_state.call_count >= 2


def test_wait_for_agent_ready_polls_until_waiting() -> None:
    """_wait_for_agent_ready should poll until agent reaches WAITING state."""
    mock_agent = Mock()
    mock_agent.name = "test-agent"

    # First few calls return RUNNING, then return WAITING
    call_count = 0

    def get_state():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            return AgentLifecycleState.RUNNING
        return AgentLifecycleState.WAITING

    mock_agent.get_lifecycle_state.side_effect = get_state

    result = _wait_for_agent_ready(mock_agent, timeout_seconds=5.0, poll_interval_seconds=0.05)

    assert result is True
    assert call_count >= 3


def test_wait_for_agent_ready_handles_stopped_state() -> None:
    """_wait_for_agent_ready should timeout if agent stays in STOPPED state."""
    mock_agent = Mock()
    mock_agent.name = "test-agent"
    mock_agent.get_lifecycle_state.return_value = AgentLifecycleState.STOPPED

    result = _wait_for_agent_ready(mock_agent, timeout_seconds=0.3, poll_interval_seconds=0.1)

    assert result is False
