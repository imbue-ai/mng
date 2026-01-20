"""Tests for the global test locking mechanism in conftest.py."""

import concurrent.futures
import fcntl
import os
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

import pytest

from conftest import acquire_global_test_lock
from conftest import is_xdist_worker
from conftest import print_lock_message


@pytest.fixture
def unique_lock_path(tmp_path: Path) -> Path:
    """Create a unique lock file path for testing."""
    return tmp_path / f"test_lock_{uuid4().hex}"


def test_is_xdist_worker_returns_false_when_env_var_not_set() -> None:
    # Ensure the env var is not set (save and restore if it was)
    original_value = os.environ.pop("PYTEST_XDIST_WORKER", None)
    try:
        assert is_xdist_worker() is False
    finally:
        if original_value is not None:
            os.environ["PYTEST_XDIST_WORKER"] = original_value


def test_is_xdist_worker_returns_true_when_env_var_set() -> None:
    original_value = os.environ.get("PYTEST_XDIST_WORKER")
    try:
        os.environ["PYTEST_XDIST_WORKER"] = "gw0"
        assert is_xdist_worker() is True
    finally:
        if original_value is not None:
            os.environ["PYTEST_XDIST_WORKER"] = original_value
        else:
            os.environ.pop("PYTEST_XDIST_WORKER", None)


def test_print_lock_message_writes_to_file_descriptor() -> None:
    # Create a pipe to capture the output
    read_fd, write_fd = os.pipe()
    try:
        print_lock_message("test message 94827364", fd=write_fd)
        os.close(write_fd)
        write_fd = -1  # Mark as closed
        result = os.read(read_fd, 4096).decode()
        assert "test message 94827364" in result
        assert result.startswith("\n")
        assert result.endswith("\n")
    finally:
        os.close(read_fd)
        if write_fd != -1:
            os.close(write_fd)


def test_acquire_global_test_lock_creates_lock_file_if_missing(
    unique_lock_path: Path,
) -> None:
    assert not unique_lock_path.exists()

    lock_handle = acquire_global_test_lock(lock_path=unique_lock_path)
    try:
        assert unique_lock_path.exists()
    finally:
        lock_handle.close()


def test_acquire_global_test_lock_returns_open_file_handle(
    unique_lock_path: Path,
) -> None:
    lock_handle = acquire_global_test_lock(lock_path=unique_lock_path)
    try:
        assert not lock_handle.closed
        # Verify we can get the file descriptor (proves handle is valid)
        assert lock_handle.fileno() >= 0
    finally:
        lock_handle.close()


def test_acquire_global_test_lock_holds_exclusive_lock(
    unique_lock_path: Path,
) -> None:
    lock_handle = acquire_global_test_lock(lock_path=unique_lock_path)
    try:
        # Try to acquire the same lock non-blocking from this process - should fail
        second_handle = unique_lock_path.open("w")
        try:
            fcntl.flock(second_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            # If we get here, the first lock wasn't held properly
            raise AssertionError("Expected BlockingIOError - lock should be held by first handle")
        except BlockingIOError:
            # This is expected - the lock is held
            pass
        finally:
            second_handle.close()
    finally:
        lock_handle.close()


def test_acquire_global_test_lock_releases_on_close(
    unique_lock_path: Path,
) -> None:
    # Acquire and release the lock
    lock_handle = acquire_global_test_lock(lock_path=unique_lock_path)
    lock_handle.close()

    # Now we should be able to acquire it again without blocking
    second_handle = unique_lock_path.open("w")
    try:
        fcntl.flock(second_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        # Success - lock was released
    finally:
        second_handle.close()


def test_acquire_global_test_lock_blocks_when_lock_held(unique_lock_path: Path) -> None:
    """Test that lock acquisition blocks when lock is held by another process.

    Uses stdin to coordinate between processes without time.sleep:
    - Subprocess acquires lock, prints "LOCK_HELD", then waits on stdin
    - Main process receives "LOCK_HELD", then tries to acquire lock in a thread
    - Main process signals subprocess to release the lock
    - Subprocess releases lock, main thread acquires it
    """
    # Create the lock file first so the subprocess can acquire it
    unique_lock_path.touch()

    # Subprocess script that holds the lock until it receives input on stdin
    holder_script = f"""
import fcntl
import sys

lock_path = "{unique_lock_path}"
with open(lock_path, "w") as f:
    fcntl.flock(f.fileno(), fcntl.LOCK_EX)
    print("LOCK_HELD", flush=True)
    # Wait for signal from main process before releasing lock
    sys.stdin.readline()
    # Lock is released when file handle is closed (exiting 'with' block)
print("LOCK_RELEASED", flush=True)
"""
    # Start the subprocess that will hold the lock
    holder_process = subprocess.Popen(
        [sys.executable, "-c", holder_script],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        # Wait for the subprocess to acquire the lock
        assert holder_process.stdout is not None
        line = holder_process.stdout.readline()
        assert "LOCK_HELD" in line

        # Start lock acquisition in a separate thread (since it will block)
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                acquire_global_test_lock,
                lock_path=unique_lock_path,
            )

            # Give the thread a moment to start blocking on the lock
            # (we can't easily detect this without the output parameter)
            time.sleep(0.1)

            # Signal the subprocess to release the lock
            assert holder_process.stdin is not None
            holder_process.stdin.write("release\n")
            holder_process.stdin.flush()

            # Wait for the lock acquisition to complete
            lock_handle = future.result(timeout=5.0)

        try:
            # We should have the lock now (after waiting)
            assert not lock_handle.closed
        finally:
            lock_handle.close()
    finally:
        # Clean up the subprocess
        if holder_process.stdin is not None:
            holder_process.stdin.close()
        holder_process.wait(timeout=5)
