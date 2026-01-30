"""Tests for shared test utilities."""

import json
import os
import subprocess
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from pathlib import Path
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from imbue.mngr.utils.polling import wait_for
from imbue.mngr.utils.testing import MODAL_TEST_ENV_PREFIX
from imbue.mngr.utils.testing import _parse_test_env_timestamp
from imbue.mngr.utils.testing import cleanup_old_modal_test_environments
from imbue.mngr.utils.testing import delete_modal_apps_in_environment
from imbue.mngr.utils.testing import delete_modal_volumes_in_environment
from imbue.mngr.utils.testing import find_old_test_environments
from imbue.mngr.utils.testing import get_subprocess_test_env
from imbue.mngr.utils.testing import list_modal_test_environments
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


# =============================================================================
# Tests for get_subprocess_test_env
# =============================================================================


def test_get_subprocess_test_env_sets_root_name() -> None:
    """get_subprocess_test_env should set MNGR_ROOT_NAME."""
    env = get_subprocess_test_env()
    assert env["MNGR_ROOT_NAME"] == "mngr-test"


def test_get_subprocess_test_env_sets_custom_root_name() -> None:
    """get_subprocess_test_env should use custom root_name when provided."""
    env = get_subprocess_test_env(root_name="mngr-custom-test")
    assert env["MNGR_ROOT_NAME"] == "mngr-custom-test"


def test_get_subprocess_test_env_sets_prefix_when_provided() -> None:
    """get_subprocess_test_env should set MNGR_PREFIX when provided."""
    env = get_subprocess_test_env(prefix="test-prefix-")
    assert env["MNGR_PREFIX"] == "test-prefix-"


def test_get_subprocess_test_env_does_not_set_prefix_when_none() -> None:
    """get_subprocess_test_env should not set MNGR_PREFIX when None."""
    env = get_subprocess_test_env(prefix=None)
    # Should not be in the env unless it was already in os.environ
    # We check that it's not different from what was originally there
    if "MNGR_PREFIX" in os.environ:
        assert env["MNGR_PREFIX"] == os.environ["MNGR_PREFIX"]
    else:
        assert "MNGR_PREFIX" not in env


def test_get_subprocess_test_env_sets_host_dir_when_provided(tmp_path: Path) -> None:
    """get_subprocess_test_env should set MNGR_HOST_DIR when provided."""
    env = get_subprocess_test_env(host_dir=tmp_path)
    assert env["MNGR_HOST_DIR"] == str(tmp_path)


def test_get_subprocess_test_env_does_not_set_host_dir_when_none() -> None:
    """get_subprocess_test_env should not set MNGR_HOST_DIR when None."""
    env = get_subprocess_test_env(host_dir=None)
    if "MNGR_HOST_DIR" in os.environ:
        assert env["MNGR_HOST_DIR"] == os.environ["MNGR_HOST_DIR"]
    else:
        assert "MNGR_HOST_DIR" not in env


def test_get_subprocess_test_env_includes_existing_environ() -> None:
    """get_subprocess_test_env should include existing os.environ variables."""
    # PATH should always exist
    env = get_subprocess_test_env()
    assert "PATH" in env
    assert env["PATH"] == os.environ["PATH"]


def test_get_subprocess_test_env_with_all_parameters(tmp_path: Path) -> None:
    """get_subprocess_test_env should set all parameters when provided."""
    env = get_subprocess_test_env(
        root_name="mngr-full-test",
        prefix="full-test-prefix-",
        host_dir=tmp_path,
    )
    assert env["MNGR_ROOT_NAME"] == "mngr-full-test"
    assert env["MNGR_PREFIX"] == "full-test-prefix-"
    assert env["MNGR_HOST_DIR"] == str(tmp_path)


# =============================================================================
# Tests for list_modal_test_environments error handling
# =============================================================================


def test_list_modal_test_environments_returns_empty_on_timeout() -> None:
    """list_modal_test_environments should return empty list on TimeoutExpired."""
    with patch("imbue.mngr.utils.testing.subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="modal", timeout=30)
        result = list_modal_test_environments()
        assert result == []


def test_list_modal_test_environments_returns_empty_on_non_zero_exit() -> None:
    """list_modal_test_environments should return empty list on non-zero exit code."""
    with patch("imbue.mngr.utils.testing.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=1,
            stderr="modal: command not found",
            stdout="",
        )
        result = list_modal_test_environments()
        assert result == []


def test_list_modal_test_environments_returns_empty_on_json_decode_error() -> None:
    """list_modal_test_environments should return empty list on JSONDecodeError."""
    with patch("imbue.mngr.utils.testing.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="not valid json",
        )
        result = list_modal_test_environments()
        assert result == []


def test_list_modal_test_environments_returns_empty_on_file_not_found() -> None:
    """list_modal_test_environments should return empty list when modal command not found."""
    with patch("imbue.mngr.utils.testing.subprocess.run") as mock_run:
        mock_run.side_effect = FileNotFoundError("modal not found")
        result = list_modal_test_environments()
        assert result == []


def test_list_modal_test_environments_filters_by_prefix() -> None:
    """list_modal_test_environments should only return environments with test prefix."""
    with patch("imbue.mngr.utils.testing.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps(
                [
                    {"name": "mngr_test-2026-01-28-14-30-45"},
                    {"name": "mngr_test-2026-01-28-15-00-00-suffix"},
                    {"name": "production-env"},
                    {"name": "dev-env"},
                    {"name": "mngr-not-a-test"},
                ]
            ),
        )
        result = list_modal_test_environments()
        assert result == [
            "mngr_test-2026-01-28-14-30-45",
            "mngr_test-2026-01-28-15-00-00-suffix",
        ]


def test_list_modal_test_environments_handles_missing_name_field() -> None:
    """list_modal_test_environments should handle environments with missing name field."""
    with patch("imbue.mngr.utils.testing.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps(
                [
                    {"name": "mngr_test-2026-01-28-14-30-45"},
                    {"other_field": "value"},
                    {"name": "mngr_test-2026-01-28-15-00-00"},
                ]
            ),
        )
        result = list_modal_test_environments()
        assert result == [
            "mngr_test-2026-01-28-14-30-45",
            "mngr_test-2026-01-28-15-00-00",
        ]


# =============================================================================
# Tests for find_old_test_environments timestamp filtering
# =============================================================================


def test_find_old_test_environments_identifies_old_environments() -> None:
    """find_old_test_environments should return environments older than max_age."""
    # Use a fixed "now" time
    fixed_now = datetime(2026, 1, 29, 12, 0, 0, tzinfo=timezone.utc)
    max_age = timedelta(hours=2)

    with patch("imbue.mngr.utils.testing.datetime") as mock_datetime:
        mock_datetime.now.return_value = fixed_now
        mock_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)

        with patch("imbue.mngr.utils.testing.list_modal_test_environments") as mock_list:
            # These are all older than 2 hours from fixed_now (12:00 UTC)
            # 08:00 = 4 hours old, 09:00 = 3 hours old, 11:00 = 1 hour old, 11:30 = 30 min old
            mock_list.return_value = [
                "mngr_test-2026-01-29-08-00-00",
                "mngr_test-2026-01-29-09-00-00",
                "mngr_test-2026-01-29-11-00-00",
                "mngr_test-2026-01-29-11-30-00",
            ]

            result = find_old_test_environments(max_age=max_age)

            assert "mngr_test-2026-01-29-08-00-00" in result
            assert "mngr_test-2026-01-29-09-00-00" in result
            assert "mngr_test-2026-01-29-11-00-00" not in result
            assert "mngr_test-2026-01-29-11-30-00" not in result


def test_find_old_test_environments_returns_empty_when_all_recent() -> None:
    """find_old_test_environments should return empty list when all environments are recent."""
    fixed_now = datetime(2026, 1, 29, 12, 0, 0, tzinfo=timezone.utc)
    max_age = timedelta(hours=1)

    with patch("imbue.mngr.utils.testing.datetime") as mock_datetime:
        mock_datetime.now.return_value = fixed_now
        mock_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)

        with patch("imbue.mngr.utils.testing.list_modal_test_environments") as mock_list:
            # Both are less than 1 hour old: 11:30 = 30 min old, 11:45 = 15 min old
            mock_list.return_value = [
                "mngr_test-2026-01-29-11-30-00",
                "mngr_test-2026-01-29-11-45-00",
            ]

            result = find_old_test_environments(max_age=max_age)
            assert result == []


def test_find_old_test_environments_returns_empty_when_no_environments() -> None:
    """find_old_test_environments should return empty list when no environments exist."""
    with patch("imbue.mngr.utils.testing.list_modal_test_environments") as mock_list:
        mock_list.return_value = []
        result = find_old_test_environments(max_age=timedelta(hours=1))
        assert result == []


# =============================================================================
# Tests for delete_modal_apps_in_environment error handling
# =============================================================================


def test_delete_modal_apps_handles_list_failure() -> None:
    """delete_modal_apps_in_environment should handle failure to list apps."""
    with patch("imbue.mngr.utils.testing.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=1,
            stderr="Environment not found",
        )
        # Should not raise an exception
        delete_modal_apps_in_environment("test-env")


def test_delete_modal_apps_handles_timeout_on_list() -> None:
    """delete_modal_apps_in_environment should handle timeout on list command."""
    with patch("imbue.mngr.utils.testing.subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="modal", timeout=30)
        # Should not raise an exception
        delete_modal_apps_in_environment("test-env")


def test_delete_modal_apps_handles_json_decode_error() -> None:
    """delete_modal_apps_in_environment should handle invalid JSON response."""
    with patch("imbue.mngr.utils.testing.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="not valid json",
        )
        # Should not raise an exception
        delete_modal_apps_in_environment("test-env")


def test_delete_modal_apps_handles_stop_timeout() -> None:
    """delete_modal_apps_in_environment should handle timeout when stopping apps."""
    with patch("imbue.mngr.utils.testing.subprocess.run") as mock_run:
        # First call returns list of apps, second call times out
        mock_run.side_effect = [
            MagicMock(
                returncode=0,
                stdout=json.dumps([{"App ID": "app-123", "Description": "Test App"}]),
            ),
            subprocess.TimeoutExpired(cmd="modal", timeout=30),
        ]
        # Should not raise an exception
        delete_modal_apps_in_environment("test-env")


def test_delete_modal_apps_stops_all_apps() -> None:
    """delete_modal_apps_in_environment should stop all apps in the environment."""
    with patch("imbue.mngr.utils.testing.subprocess.run") as mock_run:
        mock_run.side_effect = [
            MagicMock(
                returncode=0,
                stdout=json.dumps(
                    [
                        {"App ID": "app-123", "Description": "Test App 1"},
                        {"App ID": "app-456", "Description": "Test App 2"},
                    ]
                ),
            ),
            # stop app-123
            MagicMock(returncode=0),
            # stop app-456
            MagicMock(returncode=0),
        ]

        delete_modal_apps_in_environment("test-env")

        # Verify the stop commands were called with correct app IDs (calls[1] and calls[2])
        calls = mock_run.call_args_list
        assert len(calls) == 3
        assert "app-123" in calls[1][0][0]
        assert "app-456" in calls[2][0][0]


def test_delete_modal_apps_skips_apps_without_id() -> None:
    """delete_modal_apps_in_environment should skip apps without App ID field."""
    with patch("imbue.mngr.utils.testing.subprocess.run") as mock_run:
        mock_run.side_effect = [
            MagicMock(
                returncode=0,
                # App without ID and empty App ID should be skipped
                stdout=json.dumps(
                    [
                        {"App ID": "app-123", "Description": "Test App 1"},
                        {"Description": "App without ID"},
                        {"App ID": "", "Description": "Empty ID"},
                    ]
                ),
            ),
            # Only app-123 should be stopped
            MagicMock(returncode=0),
        ]

        delete_modal_apps_in_environment("test-env")

        # Only the first app (app-123) should be stopped
        calls = mock_run.call_args_list
        assert len(calls) == 2


# =============================================================================
# Tests for delete_modal_volumes_in_environment error handling
# =============================================================================


def test_delete_modal_volumes_handles_list_failure() -> None:
    """delete_modal_volumes_in_environment should handle failure to list volumes."""
    with patch("imbue.mngr.utils.testing.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=1,
            stderr="Environment not found",
        )
        # Should not raise an exception
        delete_modal_volumes_in_environment("test-env")


def test_delete_modal_volumes_handles_timeout_on_list() -> None:
    """delete_modal_volumes_in_environment should handle timeout on list command."""
    with patch("imbue.mngr.utils.testing.subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="modal", timeout=30)
        # Should not raise an exception
        delete_modal_volumes_in_environment("test-env")


def test_delete_modal_volumes_handles_json_decode_error() -> None:
    """delete_modal_volumes_in_environment should handle invalid JSON response."""
    with patch("imbue.mngr.utils.testing.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="not valid json",
        )
        # Should not raise an exception
        delete_modal_volumes_in_environment("test-env")


def test_delete_modal_volumes_handles_delete_timeout() -> None:
    """delete_modal_volumes_in_environment should handle timeout when deleting volumes."""
    with patch("imbue.mngr.utils.testing.subprocess.run") as mock_run:
        # First call returns list of volumes, second call times out
        mock_run.side_effect = [
            MagicMock(
                returncode=0,
                stdout=json.dumps([{"Name": "vol-123"}]),
            ),
            subprocess.TimeoutExpired(cmd="modal", timeout=30),
        ]
        # Should not raise an exception
        delete_modal_volumes_in_environment("test-env")


def test_delete_modal_volumes_deletes_all_volumes() -> None:
    """delete_modal_volumes_in_environment should delete all volumes in the environment."""
    with patch("imbue.mngr.utils.testing.subprocess.run") as mock_run:
        mock_run.side_effect = [
            MagicMock(
                returncode=0,
                stdout=json.dumps(
                    [
                        {"Name": "vol-123"},
                        {"Name": "vol-456"},
                    ]
                ),
            ),
            # delete vol-123
            MagicMock(returncode=0),
            # delete vol-456
            MagicMock(returncode=0),
        ]

        delete_modal_volumes_in_environment("test-env")

        # Verify the delete commands were called with correct volume names (calls[1] and calls[2])
        calls = mock_run.call_args_list
        assert len(calls) == 3
        assert "vol-123" in calls[1][0][0]
        assert "vol-456" in calls[2][0][0]


def test_delete_modal_volumes_skips_volumes_without_name() -> None:
    """delete_modal_volumes_in_environment should skip volumes without Name field."""
    with patch("imbue.mngr.utils.testing.subprocess.run") as mock_run:
        mock_run.side_effect = [
            MagicMock(
                returncode=0,
                # Volumes without Name or with empty Name should be skipped
                stdout=json.dumps(
                    [
                        {"Name": "vol-123"},
                        {"Other": "field"},
                        {"Name": ""},
                    ]
                ),
            ),
            # Only vol-123 should be deleted
            MagicMock(returncode=0),
        ]

        delete_modal_volumes_in_environment("test-env")

        # Only the first volume (vol-123) should be deleted
        calls = mock_run.call_args_list
        assert len(calls) == 2


# =============================================================================
# Tests for cleanup_old_modal_test_environments orchestration
# =============================================================================


def test_cleanup_old_modal_test_environments_returns_zero_when_no_old_envs() -> None:
    """cleanup_old_modal_test_environments should return 0 when no old environments exist."""
    with patch("imbue.mngr.utils.testing.find_old_test_environments") as mock_find:
        mock_find.return_value = []
        result = cleanup_old_modal_test_environments(max_age_hours=1.0)
        assert result == 0


def test_cleanup_old_modal_test_environments_returns_count_of_processed_envs() -> None:
    """cleanup_old_modal_test_environments should return the number of environments processed."""
    with patch("imbue.mngr.utils.testing.find_old_test_environments") as mock_find:
        mock_find.return_value = ["env-1", "env-2", "env-3"]
        with patch("imbue.mngr.utils.testing.delete_modal_apps_in_environment"):
            with patch("imbue.mngr.utils.testing.delete_modal_volumes_in_environment"):
                with patch("imbue.mngr.utils.testing.delete_modal_environment"):
                    result = cleanup_old_modal_test_environments(max_age_hours=1.0)
                    assert result == 3


def test_cleanup_old_modal_test_environments_calls_deletion_in_order() -> None:
    """cleanup_old_modal_test_environments should delete apps, then volumes, then environment."""
    call_order: list[str] = []

    def track_apps(env_name: str) -> None:
        call_order.append(f"apps:{env_name}")

    def track_volumes(env_name: str) -> None:
        call_order.append(f"volumes:{env_name}")

    def track_env(env_name: str) -> None:
        call_order.append(f"env:{env_name}")

    with patch("imbue.mngr.utils.testing.find_old_test_environments") as mock_find:
        mock_find.return_value = ["test-env-1"]
        with patch("imbue.mngr.utils.testing.delete_modal_apps_in_environment", side_effect=track_apps):
            with patch("imbue.mngr.utils.testing.delete_modal_volumes_in_environment", side_effect=track_volumes):
                with patch("imbue.mngr.utils.testing.delete_modal_environment", side_effect=track_env):
                    cleanup_old_modal_test_environments(max_age_hours=1.0)

    # Verify the order: apps first, then volumes, then environment
    assert call_order == ["apps:test-env-1", "volumes:test-env-1", "env:test-env-1"]


def test_cleanup_old_modal_test_environments_processes_all_envs() -> None:
    """cleanup_old_modal_test_environments should process all old environments."""
    processed_envs: list[str] = []

    def track_env(env_name: str) -> None:
        processed_envs.append(env_name)

    with patch("imbue.mngr.utils.testing.find_old_test_environments") as mock_find:
        mock_find.return_value = ["env-a", "env-b", "env-c"]
        with patch("imbue.mngr.utils.testing.delete_modal_apps_in_environment"):
            with patch("imbue.mngr.utils.testing.delete_modal_volumes_in_environment"):
                with patch("imbue.mngr.utils.testing.delete_modal_environment", side_effect=track_env):
                    cleanup_old_modal_test_environments(max_age_hours=1.0)

    assert processed_envs == ["env-a", "env-b", "env-c"]


def test_cleanup_old_modal_test_environments_uses_max_age_parameter() -> None:
    """cleanup_old_modal_test_environments should pass max_age to find_old_test_environments."""
    with patch("imbue.mngr.utils.testing.find_old_test_environments") as mock_find:
        mock_find.return_value = []
        cleanup_old_modal_test_environments(max_age_hours=2.5)

        # Verify that find_old_test_environments was called with the correct timedelta
        mock_find.assert_called_once()
        # max_age is passed as a positional argument
        actual_timedelta = mock_find.call_args[0][0]
        expected_timedelta = timedelta(hours=2.5)
        assert actual_timedelta == expected_timedelta
