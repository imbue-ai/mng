"""Tests for shared test utilities."""

from datetime import datetime
from datetime import timezone
from pathlib import Path

import pytest

from imbue.mngr.utils.polling import wait_for
from imbue.mngr.utils.testing import MODAL_TEST_ENV_PREFIX
from imbue.mngr.utils.testing import _parse_test_env_timestamp
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


# FIXME: This test intermittently causes pytest-xdist worker crashes when running
# with multiple workers. The crash manifests as "node down: Not properly terminated"
# and appears to be related to plugin manager initialization or cleanup. The test
# itself passes when run in isolation or with fewer parallel workers.
def test_make_mngr_ctx_creates_context_with_default_host_dir(tmp_path: Path, mngr_test_prefix: str) -> None:
    """make_mngr_ctx should create MngrContext with provided default_host_dir and prefix."""
    ctx = make_mngr_ctx(tmp_path, mngr_test_prefix)
    assert ctx.config.default_host_dir == tmp_path
    assert ctx.config.prefix == mngr_test_prefix
    assert ctx.pm is not None


# =============================================================================
# Tests for Modal test environment cleanup utilities
# =============================================================================


def test_modal_test_env_prefix_is_correct() -> None:
    """MODAL_TEST_ENV_PREFIX should have the expected value."""
    assert MODAL_TEST_ENV_PREFIX == "mngr_test-"


def test_parse_test_env_timestamp_valid_format() -> None:
    """_parse_test_env_timestamp should parse valid timestamps correctly."""
    env_name = "mngr_test-2026-01-28-14-30-45"
    result = _parse_test_env_timestamp(env_name)

    assert result is not None
    assert result.year == 2026
    assert result.month == 1
    assert result.day == 28
    assert result.hour == 14
    assert result.minute == 30
    assert result.second == 45
    assert result.tzinfo == timezone.utc


def test_parse_test_env_timestamp_with_suffix() -> None:
    """_parse_test_env_timestamp should parse timestamps even with additional suffix."""
    env_name = "mngr_test-2026-01-28-14-30-45-abc123def456"
    result = _parse_test_env_timestamp(env_name)

    assert result is not None
    assert result == datetime(2026, 1, 28, 14, 30, 45, tzinfo=timezone.utc)


def test_parse_test_env_timestamp_invalid_prefix() -> None:
    """_parse_test_env_timestamp should return None for invalid prefixes."""
    assert _parse_test_env_timestamp("invalid-2026-01-28-14-30-45") is None
    assert _parse_test_env_timestamp("mngr-2026-01-28-14-30-45") is None
    assert _parse_test_env_timestamp("test-2026-01-28-14-30-45") is None


def test_parse_test_env_timestamp_invalid_format() -> None:
    """_parse_test_env_timestamp should return None for invalid timestamp formats."""
    # Missing components
    assert _parse_test_env_timestamp("mngr_test-2026-01-28-14-30") is None
    assert _parse_test_env_timestamp("mngr_test-2026-01-28") is None
    # Wrong separators
    assert _parse_test_env_timestamp("mngr_test-2026/01/28-14:30:45") is None
    # Non-numeric values
    assert _parse_test_env_timestamp("mngr_test-abcd-01-28-14-30-45") is None


def test_parse_test_env_timestamp_empty_string() -> None:
    """_parse_test_env_timestamp should return None for empty string."""
    assert _parse_test_env_timestamp("") is None


def test_parse_test_env_timestamp_boundary_values() -> None:
    """_parse_test_env_timestamp should handle boundary date/time values."""
    # Midnight on January 1st
    result = _parse_test_env_timestamp("mngr_test-2026-01-01-00-00-00")
    assert result == datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

    # End of day on December 31st
    result = _parse_test_env_timestamp("mngr_test-2026-12-31-23-59-59")
    assert result == datetime(2026, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
