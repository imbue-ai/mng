# FIXME0: Replace usages of MagicMock, Mock, patch, etc with better testing patterns like we did in create_test.py
"""Tests for the watch mode utility."""

from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from imbue.mngr.cli.watch_mode import run_watch_loop
from imbue.mngr.errors import MngrError


def test_run_watch_loop_runs_iteration_function() -> None:
    """run_watch_loop should call the iteration function."""
    mock_fn = MagicMock()
    call_count = [0]

    def iteration_fn() -> None:
        call_count[0] += 1
        if call_count[0] >= 2:
            raise KeyboardInterrupt()
        mock_fn()

    with patch("imbue.mngr.cli.watch_mode.wait_for"):
        with pytest.raises(KeyboardInterrupt):
            run_watch_loop(iteration_fn, interval_seconds=5)

    # Should have called the function at least once before KeyboardInterrupt
    assert mock_fn.call_count >= 1


def test_run_watch_loop_waits_between_iterations() -> None:
    """run_watch_loop should wait for the specified interval between iterations."""
    call_count = [0]

    def iteration_fn() -> None:
        call_count[0] += 1
        if call_count[0] >= 2:
            raise KeyboardInterrupt()

    with patch("imbue.mngr.cli.watch_mode.wait_for") as mock_wait:
        with pytest.raises(KeyboardInterrupt):
            run_watch_loop(iteration_fn, interval_seconds=10)

    # Should have waited at least once
    assert mock_wait.call_count >= 1
    # Check that timeout was set to the interval
    call_kwargs = mock_wait.call_args_list[0][1]
    assert call_kwargs["timeout"] == 10.0


def test_run_watch_loop_continues_on_mngr_error_by_default() -> None:
    """run_watch_loop should continue on MngrError when on_error_continue is True."""
    call_count = [0]

    def iteration_fn() -> None:
        call_count[0] += 1
        if call_count[0] == 1:
            raise MngrError("Test error")
        if call_count[0] >= 3:
            raise KeyboardInterrupt()

    with patch("imbue.mngr.cli.watch_mode.wait_for"):
        with pytest.raises(KeyboardInterrupt):
            run_watch_loop(iteration_fn, interval_seconds=1, on_error_continue=True)

    # Should have continued past the error
    assert call_count[0] >= 2


def test_run_watch_loop_stops_on_mngr_error_when_configured() -> None:
    """run_watch_loop should re-raise MngrError when on_error_continue is False."""
    call_count = [0]

    def iteration_fn() -> None:
        call_count[0] += 1
        raise MngrError("Test error")

    with patch("imbue.mngr.cli.watch_mode.wait_for"):
        with pytest.raises(MngrError, match="Test error"):
            run_watch_loop(iteration_fn, interval_seconds=1, on_error_continue=False)

    # Should have stopped after the first error
    assert call_count[0] == 1
