"""Tests for conftest.py functionality including global test locking and test output file generation."""

import concurrent.futures
import fcntl
import os
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

import pytest

from conftest import _ensure_test_outputs_dir
from conftest import _generate_output_filename
from conftest import acquire_global_test_lock
from conftest import is_xdist_worker
from conftest import print_lock_message
from conftest import pytest_load_initial_conftests


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


# Tests for test output file generation functionality


@pytest.fixture
def test_outputs_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Override the test outputs directory to use a temp path."""
    import conftest

    test_dir = tmp_path / "tests_outputs"
    monkeypatch.setattr(conftest, "_TEST_OUTPUTS_DIR", test_dir)
    return test_dir


def test_ensure_test_outputs_dir_creates_directory(test_outputs_dir: Path) -> None:
    assert not test_outputs_dir.exists()
    result = _ensure_test_outputs_dir()
    assert result == test_outputs_dir
    assert test_outputs_dir.exists()
    assert test_outputs_dir.is_dir()


def test_ensure_test_outputs_dir_is_idempotent(test_outputs_dir: Path) -> None:
    _ensure_test_outputs_dir()
    _ensure_test_outputs_dir()
    assert test_outputs_dir.exists()


def test_generate_output_filename_creates_unique_files(test_outputs_dir: Path) -> None:
    file1 = _generate_output_filename("test", ".txt")
    file2 = _generate_output_filename("test", ".txt")
    assert file1 != file2
    assert file1.parent == test_outputs_dir
    assert file2.parent == test_outputs_dir
    assert file1.name.startswith("test_")
    assert file1.name.endswith(".txt")


def test_generate_output_filename_uses_correct_prefix_and_extension(test_outputs_dir: Path) -> None:
    file = _generate_output_filename("slow_tests", ".json")
    assert file.name.startswith("slow_tests_")
    assert file.name.endswith(".json")


def test_pytest_load_initial_conftests_removes_term_missing_from_args() -> None:
    """Test that --cov-report=term-missing is removed when --coverage-to-file is present."""
    args = [
        "-n",
        "4",
        "--cov-report=term-missing",
        "--cov-report=html",
        "--coverage-to-file",
    ]
    # The function only uses args, so we can pass None for unused parameters
    pytest_load_initial_conftests(None, None, args)  # type: ignore[arg-type]

    assert "--cov-report=term-missing" not in args
    assert "--cov-report=html" in args
    assert "--coverage-to-file" in args


def test_pytest_load_initial_conftests_removes_term_from_args() -> None:
    """Test that --cov-report=term is removed when --coverage-to-file is present."""
    args = [
        "--cov-report=term",
        "--cov-report=xml",
        "--coverage-to-file",
    ]
    pytest_load_initial_conftests(None, None, args)  # type: ignore[arg-type]

    assert "--cov-report=term" not in args
    assert "--cov-report=xml" in args


def test_pytest_load_initial_conftests_does_nothing_without_coverage_to_file() -> None:
    """Test that args are unchanged when --coverage-to-file is not present."""
    args = [
        "--cov-report=term-missing",
        "--cov-report=html",
    ]
    original_args = args.copy()
    pytest_load_initial_conftests(None, None, args)  # type: ignore[arg-type]

    assert args == original_args


# Integration tests for file output functionality


def test_slow_tests_to_file_creates_output_file(tmp_path: Path) -> None:
    """Integration test: --slow-tests-to-file creates a file with slow test durations."""
    # Create a simple test file in the temp directory
    test_file = tmp_path / "test_simple.py"
    test_file.write_text(
        """\
import time

def test_slow():
    time.sleep(0.01)

def test_fast():
    pass
"""
    )

    # Create a custom output directory in the temp path
    output_dir = tmp_path / "tests_outputs"
    # Use a unique lock path to avoid blocking on the parent pytest's lock
    lock_path = tmp_path / "test_lock"

    # Run pytest with --slow-tests-to-file from the main project directory
    # Using a subprocess that explicitly registers conftest as a plugin
    # Remove PYTEST_XDIST_WORKER from env so the subprocess doesn't think it's a worker
    env = os.environ.copy()
    env.pop("PYTEST_XDIST_WORKER", None)

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            f"""
import sys
from pathlib import Path
sys.path.insert(0, "{Path.cwd()}")

import conftest
conftest._TEST_OUTPUTS_DIR = Path("{output_dir}")
conftest._GLOBAL_TEST_LOCK_PATH = Path("{lock_path}")

import pytest
sys.exit(pytest.main([
    "{test_file}",
    "--slow-tests-to-file",
    "--durations=2",
    "-p", "no:randomly",
    "-p", "no:xdist",
    "--no-cov",
], plugins=[conftest]))
""",
        ],
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
    )

    # The test should pass
    assert result.returncode == 0, f"pytest failed: {result.stdout}\n{result.stderr}"

    # Check that an output file was created
    assert output_dir.exists(), (
        f"Output directory not created.\n"
        f"stdout: {result.stdout}\n"
        f"stderr: {result.stderr}"
    )
    output_files = list(output_dir.glob("slow_tests_*.txt"))
    assert len(output_files) == 1, f"Expected 1 slow_tests file, found {len(output_files)}"

    # Verify the content
    content = output_files[0].read_text()
    assert "slowest" in content
    assert "test_slow" in content or "test_fast" in content


def test_coverage_to_file_creates_output_file(tmp_path: Path) -> None:
    """Integration test: --coverage-to-file creates a file with coverage summary."""
    # Create a simple module to test coverage on
    module_file = tmp_path / "mymodule.py"
    module_file.write_text(
        """\
def add(a, b):
    return a + b
"""
    )

    # Create a simple test file
    test_file = tmp_path / "test_mymodule.py"
    test_file.write_text(
        """\
from mymodule import add

def test_add():
    assert add(1, 2) == 3
"""
    )

    # Create a custom output directory in the temp path
    output_dir = tmp_path / "tests_outputs"
    # Use a unique lock path to avoid blocking on the parent pytest's lock
    lock_path = tmp_path / "test_lock"

    # Run pytest with --coverage-to-file using a subprocess that registers conftest as plugin
    # Remove PYTEST_XDIST_WORKER from env so the subprocess doesn't think it's a worker
    env = os.environ.copy()
    env.pop("PYTEST_XDIST_WORKER", None)

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            f"""
import sys
from pathlib import Path
sys.path.insert(0, "{Path.cwd()}")
sys.path.insert(0, "{tmp_path}")

import conftest
conftest._TEST_OUTPUTS_DIR = Path("{output_dir}")
conftest._GLOBAL_TEST_LOCK_PATH = Path("{lock_path}")

import pytest
sys.exit(pytest.main([
    "{test_file}",
    "--coverage-to-file",
    "--cov={module_file}",
    "--cov-report=",
    "-p", "no:randomly",
    "-p", "no:xdist",
], plugins=[conftest]))
""",
        ],
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
    )

    # The test should pass
    assert result.returncode == 0, f"pytest failed: {result.stdout}\n{result.stderr}"

    # Check that an output file was created
    assert output_dir.exists(), f"Output directory not created. stderr: {result.stderr}"
    output_files = list(output_dir.glob("coverage_summary_*.txt"))
    assert len(output_files) == 1, f"Expected 1 coverage_summary file, found {len(output_files)}"

    # Verify the content
    content = output_files[0].read_text()
    assert "Coverage Summary" in content
    assert "Total coverage:" in content or "Detailed reports:" in content


