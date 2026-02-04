"""Unit tests for the polling module."""

import time

from imbue.mngr.utils.polling import poll_until


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
