"""Unit tests for the polling module."""

import time

import pytest

from imbue.mng.utils.polling import poll_until
from imbue.mng.utils.polling import wait_for


def test_poll_until_returns_true_when_condition_met() -> None:
    """poll_until should return True when condition is met immediately."""
    result = poll_until(lambda: True, timeout=1.0)

    assert result is True


def test_poll_until_returns_false_on_timeout() -> None:
    """poll_until should return False when timeout expires without condition being met."""
    result = poll_until(lambda: False, timeout=0.3, poll_interval=0.1)

    assert result is False


def test_poll_until_polls_until_condition_met() -> None:
    """poll_until should poll until condition is met."""
    start = time.time()

    result = poll_until(lambda: time.time() - start > 0.15, timeout=1.0, poll_interval=0.05)
    elapsed = time.time() - start
    assert result is True
    assert elapsed > 0.15
    assert elapsed < 0.75


def test_wait_for_returns_immediately_when_condition_true() -> None:
    """wait_for should return immediately when condition is already true."""
    wait_for(lambda: True, timeout=1.0)


def test_wait_for_raises_timeout_error_when_condition_never_true() -> None:
    """wait_for should raise TimeoutError when condition never becomes true."""
    with pytest.raises(TimeoutError, match="Condition not met"):
        wait_for(lambda: False, timeout=0.1, poll_interval=0.05, error_message="Condition not met")


def test_wait_for_custom_error_message() -> None:
    """wait_for should use custom error message."""
    with pytest.raises(TimeoutError, match="Custom error"):
        wait_for(lambda: False, timeout=0.1, poll_interval=0.05, error_message="Custom error")
