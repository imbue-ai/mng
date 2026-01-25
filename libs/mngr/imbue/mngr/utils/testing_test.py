"""Tests for shared test utilities."""

from pathlib import Path

import pytest

from imbue.mngr.utils.polling import wait_for
from imbue.mngr.utils.testing import make_mngr_ctx


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


def test_make_mngr_ctx_creates_context_with_default_host_dir(tmp_path: Path, mngr_test_prefix: str) -> None:
    """make_mngr_ctx should create MngrContext with provided default_host_dir and prefix."""
    ctx = make_mngr_ctx(tmp_path, mngr_test_prefix)
    assert ctx.config.default_host_dir == tmp_path
    assert ctx.config.prefix == mngr_test_prefix
    assert ctx.pm is not None
