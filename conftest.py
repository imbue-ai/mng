"""Root conftest for enforcing test suite time limits and global test locking."""

import fcntl
import os
import time
from pathlib import Path
from typing import Final
from typing import TextIO

import pytest

# The lock file path - a constant location in /tmp so all pytest processes can find it
_GLOBAL_TEST_LOCK_PATH: Final[Path] = Path("/tmp/pytest_global_test_lock")

# Attribute name used to store the lock file handle on the session object.
# The handle must stay open for the duration of the test session so the flock is held.
# When the process exits for any reason, the OS closes the handle and releases the lock.
_SESSION_LOCK_HANDLE_ATTR: Final[str] = "_global_test_lock_file_handle"


def is_xdist_worker() -> bool:
    """Return True if we are running as an xdist worker process."""
    return "PYTEST_XDIST_WORKER" in os.environ


def print_lock_message(message: str, fd: int = 2) -> None:
    """Print a message that will show even without pytest's -s flag.

    Writes directly to the file descriptor (default: 2 = stderr) to bypass
    any output capturing that pytest or xdist may be doing.
    """
    os.write(fd, f"\n{message}\n".encode())


def acquire_global_test_lock(
    lock_path: Path,
) -> TextIO:
    """Acquire an exclusive lock on the given path, returning the open file handle.

    If the lock cannot be acquired immediately, prints a waiting message to stderr,
    then blocks until the lock is available.

    The caller must keep the returned file handle open for as long as they want to hold
    the lock. The lock is automatically released when the file handle is closed or when
    the process exits.
    """
    # Create the lock file if it doesn't exist
    lock_path.touch(exist_ok=True)

    # Open the lock file
    lock_file_handle = lock_path.open("w")

    # Try to acquire the lock without blocking first to see if we need to wait
    try:
        fcntl.flock(lock_file_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        # We got the lock immediately, no need to print anything
        return lock_file_handle
    except BlockingIOError:
        # Lock is held by another process, we'll need to wait
        pass

    # Print a message about waiting for the lock
    print_lock_message(
        "PYTEST GLOBAL LOCK: Another pytest process is running.\n"
        "Waiting for it to complete before starting this test run...",
    )

    # Now acquire the lock with blocking (will wait until available)
    fcntl.flock(lock_file_handle.fileno(), fcntl.LOCK_EX)

    print_lock_message("PYTEST GLOBAL LOCK: Lock acquired, proceeding with tests.")

    return lock_file_handle


@pytest.hookimpl(tryfirst=True)
def pytest_sessionstart(session: pytest.Session) -> None:
    """Acquire the global test lock and record the start time.

    The lock prevents multiple parallel pytest processes (e.g., from different worktrees)
    from running tests concurrently, which can cause timing-related flaky tests.

    The lock is acquired at session start (before collection) because with xdist,
    the controller process doesn't run pytest_collection_finish - only workers do.
    By acquiring the lock here, we ensure the controller holds it for the entire session.

    xdist workers skip lock acquisition since the controller already holds it.

    IMPORTANT: The start_time is set AFTER the lock is acquired so that time spent
    waiting for the lock is not counted against the test suite time limit.
    """
    # xdist workers should not acquire the lock - only the controller does
    if is_xdist_worker():
        setattr(session, "start_time", time.time())
        return

    # Acquire the lock and store the handle on the session to keep it open
    lock_handle = acquire_global_test_lock(lock_path=_GLOBAL_TEST_LOCK_PATH)
    setattr(session, _SESSION_LOCK_HANDLE_ATTR, lock_handle)

    # Record start time AFTER acquiring the lock so wait time isn't counted
    setattr(session, "start_time", time.time())


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session, exitstatus):
    """Check that the total test session time is under the configured limit."""
    if hasattr(session, "start_time"):
        duration = time.time() - session.start_time

        # Allow explicit override via environment variable (useful for generating test timings)
        if "PYTEST_MAX_DURATION" in os.environ:
            max_duration = float(os.environ["PYTEST_MAX_DURATION"])
        elif "CI" in os.environ:
            # There are 4 types of tests, each with different time limits in CI:
            # - unit tests: fast, local, no network (run with integration tests)
            # - integration tests: local, no network, used for coverage calculation
            # - acceptance tests: run on all branches except main, have network/Modal access
            # - release tests: only run on main, comprehensive tests for release readiness
            if os.environ.get("IS_RELEASE", "0") == "1":
                # Release tests (only on main): highest limit since they're comprehensive and can take a long time
                max_duration = 10 * 60.0
            elif os.environ.get("IS_ACCEPTANCE", "0") == "1":
                # Acceptance tests (all branches except main): higher limit for tests with network/Modal access
                max_duration = 5 * 60.0
            else:
                # Unit + Integration tests: used for coverage, should be fast
                max_duration = 60.0
        else:
            # Local test runs: applies to the entire test suite (unit + integration) when run locally
            max_duration = 35.0

        if duration > max_duration:
            pytest.exit(
                f"Test suite took {duration:.2f}s, exceeding the {max_duration}s limit",
                returncode=1,
            )
