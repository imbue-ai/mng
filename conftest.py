"""Root conftest for enforcing test suite time limits and global test locking."""

import fcntl
import os
import time
from pathlib import Path
from typing import Final
from typing import TextIO
from uuid import uuid4

import pytest
from coverage.exceptions import CoverageException

# Directory for test output files (slow tests, coverage summaries)
_TEST_OUTPUTS_DIR: Final[Path] = Path(".claude/tests_outputs")

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
            # acceptance tests have a higher limit, since there can be many more of them, and they can take longer
            if os.environ.get("IS_ACCEPTANCE", "0") == "1":
                # this limit applies to the test suite that runs against "main" in GitHub CI
                max_duration = 5 * 60.0
            # integration tests have a lower limit
            else:
                # this limit applies to the test suite that runs against all branches *except* "main" in GitHub CI
                max_duration = 60.0
        else:
            # this limit applies to the entire test suite when run locally
            max_duration = 35.0

        if duration > max_duration:
            pytest.exit(
                f"Test suite took {duration:.2f}s, exceeding the {max_duration}s limit",
                returncode=1,
            )


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add options for redirecting slow tests and coverage output to files."""
    group = parser.getgroup("output-to-file", "Options for redirecting output to files")
    group.addoption(
        "--slow-tests-to-file",
        action="store_true",
        default=False,
        help="Write slow tests report to a file instead of stdout",
    )
    group.addoption(
        "--coverage-to-file",
        action="store_true",
        default=False,
        help="Write coverage summary to a file instead of stdout",
    )


def _ensure_test_outputs_dir() -> Path:
    """Ensure the test outputs directory exists and return its path."""
    _TEST_OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    return _TEST_OUTPUTS_DIR


def _generate_output_filename(prefix: str, extension: str) -> Path:
    """Generate a unique filename for test output."""
    return _ensure_test_outputs_dir() / f"{prefix}_{uuid4().hex}{extension}"


def pytest_load_initial_conftests(
    early_config: pytest.Config,
    parser: pytest.Parser,
    args: list[str],
) -> None:
    """Modify coverage options early, before pytest-cov processes them."""
    # Check if --coverage-to-file is in the args
    if "--coverage-to-file" in args:
        # Find and remove term-based coverage reports from the args
        # We need to handle both explicit args and those from addopts
        indices_to_remove: list[int] = []
        i = 0
        while i < len(args):
            arg = args[i]
            # Handle --cov-report=term-missing form
            if arg.startswith("--cov-report=term"):
                indices_to_remove.append(i)
            # Handle --cov-report term-missing form (two separate args)
            elif arg == "--cov-report" and i + 1 < len(args) and args[i + 1].startswith("term"):
                indices_to_remove.append(i)
                indices_to_remove.append(i + 1)
                i += 1
            i += 1

        # Remove in reverse order to preserve indices
        for idx in reversed(indices_to_remove):
            args.pop(idx)


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config: pytest.Config) -> None:
    """Store options on config for later use and suppress terminal output when redirecting to files."""
    # Store the slow-tests-to-file option on config for use in hooks
    slow_tests_to_file = config.getoption("--slow-tests-to-file", default=False)
    coverage_to_file = config.getoption("--coverage-to-file", default=False)
    setattr(config, "_slow_tests_to_file", slow_tests_to_file)
    setattr(config, "_coverage_to_file", coverage_to_file)

    # Save the original durations count for our custom reporting, then suppress terminal output
    if slow_tests_to_file:
        original_durations = config.getoption("durations", default=0)
        setattr(config, "_original_durations", original_durations)
        # Set durations to None to suppress pytest's built-in terminal output
        # Note: durations=0 shows ALL durations, durations=None suppresses the output
        config.option.durations = None

    # Suppress coverage terminal output when redirecting to file
    if coverage_to_file:
        # Remove term-missing from cov_report options to suppress terminal output
        # but keep html and xml reports
        cov_report = getattr(config.option, "cov_report", None)
        if cov_report is not None and isinstance(cov_report, dict):
            cov_report.pop("term-missing", None)
            cov_report.pop("term", None)


@pytest.hookimpl(trylast=True)
def pytest_terminal_summary(
    terminalreporter: "pytest.TerminalReporter",
    exitstatus: int,
    config: pytest.Config,
) -> None:
    """Write slow tests to file if the option is enabled."""
    # Only run on the controller process (not xdist workers)
    if is_xdist_worker():
        return

    slow_tests_to_file = getattr(config, "_slow_tests_to_file", False)
    coverage_to_file = getattr(config, "_coverage_to_file", False)

    # Handle slow tests output
    if slow_tests_to_file:
        _write_slow_tests_to_file(terminalreporter, config)

    # Handle coverage output
    if coverage_to_file:
        _write_coverage_summary_to_file(terminalreporter, config)


def _write_slow_tests_to_file(
    terminalreporter: "pytest.TerminalReporter",
    config: pytest.Config,
) -> None:
    """Write the slow tests report to a file."""
    # Get durations from the terminal reporter's stats (aggregated from all workers)
    # This works with xdist because the controller aggregates results from workers
    durations: list[tuple[float, str]] = []

    # Collect durations from test reports in the stats
    for reports in terminalreporter.stats.values():
        for report in reports:
            if hasattr(report, "duration") and hasattr(report, "nodeid"):
                # Only count the "call" phase (not setup/teardown)
                if getattr(report, "when", None) == "call":
                    durations.append((report.duration, report.nodeid))

    # Sort by duration (slowest first)
    durations = sorted(durations, reverse=True)

    # Get the original durations count (saved before we suppressed terminal output)
    durations_count = getattr(config, "_original_durations", 0)
    if durations_count and durations_count > 0:
        durations = durations[:durations_count]

    if not durations:
        return

    # Generate output file
    output_file = _generate_output_filename("slow_tests", ".txt")

    # Write the report
    lines = [f"slowest {len(durations)} durations", ""]
    for duration, nodeid in durations:
        lines.append(f"{duration:.4f}s {nodeid}")

    output_file.write_text("\n".join(lines))

    # Print single line indicating where the file was saved
    print_lock_message(f"Slow tests report saved to: {output_file}")


def _write_coverage_summary_to_file(
    terminalreporter: "pytest.TerminalReporter",
    config: pytest.Config,
) -> None:
    """Write the coverage summary to a file.

    This captures a summary of coverage including the existing HTML/XML reports
    and writes a pointer to those locations.
    """
    # Check if coverage plugin is active
    cov_plugin = config.pluginmanager.get_plugin("_cov")
    if cov_plugin is None:
        return

    # Generate output file
    output_file = _generate_output_filename("coverage_summary", ".txt")

    lines = ["Coverage Summary", ""]

    # Get the coverage object from pytest-cov
    cov = getattr(cov_plugin, "cov_controller", None)
    if cov is not None:
        cov_obj = getattr(cov, "cov", None)
        if cov_obj is not None:
            try:
                # Get total coverage percentage
                total = cov_obj.report(file=None, show_missing=False)
                lines.append(f"Total coverage: {total:.2f}%")
            except CoverageException:
                lines.append("Total coverage: (unable to calculate)")

    # Add pointers to the detailed reports
    lines.append("")
    lines.append("Detailed reports:")
    lines.append("  HTML report: htmlcov/index.html")
    lines.append("  XML report: coverage.xml")

    output_file.write_text("\n".join(lines))

    # Print single line indicating where the file was saved
    print_lock_message(f"Coverage summary saved to: {output_file}")
