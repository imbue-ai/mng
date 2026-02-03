"""Unit tests for the create API."""

from imbue.mngr.primitives import AgentLifecycleState
from imbue.mngr.utils.polling import poll_until


def test_poll_until_returns_true_when_condition_met() -> None:
    """poll_until should return True when condition is met."""
    result = poll_until(lambda: True, timeout=1.0)

    assert result is True


def test_poll_until_returns_false_on_timeout() -> None:
    """poll_until should return False when timeout expires without condition being met."""
    result = poll_until(lambda: False, timeout=0.3, poll_interval=0.1)

    assert result is False


def test_poll_until_polls_until_condition_met() -> None:
    """poll_until should poll until condition is met."""
    call_count = 0

    def condition():
        nonlocal call_count
        call_count += 1
        return call_count >= 3

    result = poll_until(condition, timeout=5.0, poll_interval=0.05)

    assert result is True
    assert call_count >= 3


def test_poll_until_with_lifecycle_state_condition() -> None:
    """poll_until should work with agent lifecycle state checks."""
    states = [AgentLifecycleState.RUNNING, AgentLifecycleState.RUNNING, AgentLifecycleState.WAITING]
    call_count = 0

    def get_state():
        nonlocal call_count
        state = states[min(call_count, len(states) - 1)]
        call_count += 1
        return state

    result = poll_until(lambda: get_state() == AgentLifecycleState.WAITING, timeout=5.0, poll_interval=0.05)

    assert result is True
