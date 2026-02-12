"""Shared pytest conftest hooks for all projects in the monorepo.

Provides common test infrastructure:
- Global test locking (prevents parallel pytest processes from conflicting)
- Test suite timing limits
- Output file redirection (slow tests report, coverage report)

Usage in each project's conftest.py:
    from imbue.imbue_common.conftest_hooks import register_conftest_hooks
    register_conftest_hooks(globals())

The register_conftest_hooks function uses a module-level guard to ensure hooks
are only registered once. This is critical because when running from the monorepo
root, both the root conftest.py AND per-project conftest.py files are discovered
by pytest. Without the guard, pytest_addoption would fail with duplicate option errors.
"""

import fcntl
import os
import time
from io import StringIO
from pathlib import Path
from typing import Final
from typing import TextIO
from uuid import uuid4

import pytest
from coverage.exceptions import CoverageException

# Directory for test output files (slow tests, coverage summaries).
# Relative to wherever pytest is invoked from.
_TEST_OUTPUTS_DIR: Final[Path] = Path(".test_output")

# The lock file path - a constant location in /tmp so all pytest processes can find it
_GLOBAL_TEST_LOCK_PATH: Final[Path] = Path("/tmp/pytest_global_test_lock")

# Attribute name used to store the lock file handle on the session object.
# The handle must stay open for the duration of the test session so the flock is held.
# When the process exits for any reason, the OS closes the handle and releases the lock.
_SESSION_LOCK_HANDLE_ATTR: Final[str] = "_global_test_lock_file_handle"

# Guard to prevent duplicate hook registration (see module docstring).
_registered: bool = False


def _is_xdist_worker() -> bool:
    """Return True if we are running as an xdist worker process."""
    return "PYTEST_XDIST_WORKER" in os.environ


def _print_lock_message(message: str, fd: int = 2) -> None:
    """Print a message that will show even without pytest's -s flag.

    Writes directly to the file descriptor (default: 2 = stderr) to bypass
    any output capturing that pytest or xdist may be doing.
    """
    os.write(fd, f"\n{message}\n".encode())


def _acquire_global_test_lock(
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
    _print_lock_message(
        "PYTEST GLOBAL LOCK: Another pytest process is running.\n"
        "Waiting for it to complete before starting this test run...",
    )

    # Now acquire the lock with blocking (will wait until available)
    fcntl.flock(lock_file_handle.fileno(), fcntl.LOCK_EX)

    _print_lock_message("PYTEST GLOBAL LOCK: Lock acquired, proceeding with tests.")

    return lock_file_handle


# ---------------------------------------------------------------------------
# Pytest hook implementations (prefixed with _ to avoid accidental discovery)
# ---------------------------------------------------------------------------


@pytest.hookimpl(tryfirst=True)
def _pytest_sessionstart(session: pytest.Session) -> None:
    """Acquire the global test lock, record the start time, and finalize coverage suppression.

    Coverage suppression is done here because pytest-cov's CovController is created
    in pytest_configure, but conftest.py's pytest_configure runs after installed plugins.
    By the time our pytest_configure runs, pytest-cov has already copied the cov_report options.
    We modify the CovController here to ensure the terminal report is suppressed.

    The lock prevents multiple parallel pytest processes (e.g., from different worktrees)
    from running tests concurrently, which can cause timing-related flaky tests.

    The lock is acquired at session start (before collection) because with xdist,
    the controller process doesn't run pytest_collection_finish - only workers do.
    By acquiring the lock here, we ensure the controller holds it for the entire session.

    xdist workers skip lock acquisition since the controller already holds it.

    IMPORTANT: The start_time is set AFTER the lock is acquired so that time spent
    waiting for the lock is not counted against the test suite time limit.
    """
    # Suppress coverage terminal output if --coverage-to-file is enabled
    # This needs to be done here because pytest-cov's CovController is created
    # in pytest_configure, after conftest.py's hooks run
    coverage_to_file = getattr(session.config, "_coverage_to_file", False)
    if coverage_to_file:
        cov_plugin = session.config.pluginmanager.get_plugin("_cov")
        if cov_plugin is not None:
            cov_controller = getattr(cov_plugin, "cov_controller", None)
            if cov_controller is not None:
                controller_cov_report = getattr(cov_controller, "cov_report", None)
                if controller_cov_report is not None and isinstance(controller_cov_report, dict):
                    controller_cov_report.pop("term-missing", None)
                    controller_cov_report.pop("term", None)

    # xdist workers should not acquire the lock - only the controller does
    if _is_xdist_worker():
        # Use setattr to avoid type errors - pytest Session doesn't declare these attributes
        setattr(session, "start_time", time.time())  # noqa: B010
        return

    # Acquire the lock and store the handle on the session to keep it open
    lock_handle = _acquire_global_test_lock(lock_path=_GLOBAL_TEST_LOCK_PATH)
    setattr(session, _SESSION_LOCK_HANDLE_ATTR, lock_handle)  # noqa: B010

    # Record start time AFTER acquiring the lock so wait time isn't counted
    setattr(session, "start_time", time.time())  # noqa: B010


@pytest.hookimpl(trylast=True)
def _pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Check that the total test session time is under the configured limit."""
    if hasattr(session, "start_time"):
        duration = time.time() - session.start_time

        # There are 4 types of tests, each with different time limits in CI:
        # - unit tests: fast, local, no network (run with integration tests)
        # - integration tests: local, no network, used for coverage calculation
        # - acceptance tests: run on all branches except main, have network/Modal/etc access
        # - release tests: only run on main, comprehensive tests for release readiness

        # Allow explicit override via environment variable (useful for generating test timings)
        if "PYTEST_MAX_DURATION" in os.environ:
            max_duration = float(os.environ["PYTEST_MAX_DURATION"])
        # release tests have the highest limit, since there can be many more of them, and they can take a really long time
        elif os.environ.get("IS_RELEASE", "0") == "1":
            # this limit applies to the test suite that runs against "main" in GitHub CI
            max_duration = 10 * 60.0
        # acceptance tests have a somewhat higher limit (than integration and unit)
        elif os.environ.get("IS_ACCEPTANCE", "0") == "1":
            # this limit applies to the test suite that runs against all branches *except* "main" in GitHub CI (and has access to network, Modal, etc)
            max_duration = 6 * 60.0
        # integration tests have a lower limit
        else:
            if "CI" in os.environ:
                # this limit applies to the test suite that runs against all branches *except* "main" in GitHub CI (and which is basically just used for calculating coverage)
                # typically integration tests and unit tests are run locally, so we want them to be fast
                max_duration = 80.0
            else:
                # this limit applies to the entire test suite when run locally
                max_duration = 300.0

        if duration > max_duration:
            pytest.exit(
                f"Test suite took {duration:.2f}s, exceeding the {max_duration}s limit",
                returncode=1,
            )


def _pytest_addoption(parser: pytest.Parser) -> None:
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


def _pytest_load_initial_conftests(
    early_config: pytest.Config,
    parser: pytest.Parser,
    args: list[str],
) -> None:
    """Modify coverage options early, before pytest-cov processes them.

    Note: This hook runs before conftest.py is loaded, so it doesn't actually
    execute from conftest.py. It's kept here for documentation purposes and
    in case it's registered as a plugin.
    """
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
def _pytest_configure(config: pytest.Config) -> None:
    """Store options on config for later use and suppress terminal output when redirecting to files."""
    # Store the slow-tests-to-file option on config for use in hooks
    # Use setattr to avoid type errors - pytest Config doesn't declare these private attributes
    slow_tests_to_file = config.getoption("--slow-tests-to-file", default=False)
    coverage_to_file = config.getoption("--coverage-to-file", default=False)
    setattr(config, "_slow_tests_to_file", slow_tests_to_file)  # noqa: B010
    setattr(config, "_coverage_to_file", coverage_to_file)  # noqa: B010

    # Save the original durations count for our custom reporting, then suppress terminal output
    if slow_tests_to_file:
        original_durations = config.getoption("durations", default=0)
        setattr(config, "_original_durations", original_durations)  # noqa: B010
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

        # Also modify pytest-cov's internal CovController if it exists
        # (it may have already copied the options)
        cov_plugin = config.pluginmanager.get_plugin("_cov")
        if cov_plugin is not None:
            cov_controller = getattr(cov_plugin, "cov_controller", None)
            if cov_controller is not None:
                controller_cov_report = getattr(cov_controller, "cov_report", None)
                if controller_cov_report is not None and isinstance(controller_cov_report, dict):
                    controller_cov_report.pop("term-missing", None)
                    controller_cov_report.pop("term", None)


@pytest.hookimpl(trylast=True)
def _pytest_terminal_summary(
    terminalreporter: "pytest.TerminalReporter",
    exitstatus: int,
    config: pytest.Config,
) -> None:
    """Write slow tests to file if the option is enabled."""
    # Only run on the controller process (not xdist workers)
    if _is_xdist_worker():
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
    _print_lock_message(f"Slow tests report saved to: {output_file}")


def _write_coverage_summary_to_file(
    terminalreporter: "pytest.TerminalReporter",
    config: pytest.Config,
) -> None:
    """Write the full coverage report (term-missing format) to a file.

    This captures the same output that would be printed to terminal with
    --cov-report=term-missing and writes it to a file instead.
    """
    # Check if coverage plugin is active
    cov_plugin = config.pluginmanager.get_plugin("_cov")
    if cov_plugin is None:
        return

    # Get the coverage object from pytest-cov
    cov_controller = getattr(cov_plugin, "cov_controller", None)
    if cov_controller is None:
        return

    cov_obj = getattr(cov_controller, "cov", None)
    if cov_obj is None:
        return

    # Generate output file
    output_file = _generate_output_filename("coverage", ".txt")

    try:
        # Capture the full term-missing report to a StringIO
        report_output = StringIO()
        cov_obj.report(file=report_output, show_missing=True)
        report_content = report_output.getvalue()

        if report_content:
            output_file.write_text(report_content)
            _print_lock_message(f"Coverage report saved to: {output_file}")
    except CoverageException:
        # If we can't generate the report, don't create an empty file
        pass


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_conftest_hooks(namespace: dict) -> None:
    """Register the common conftest hooks into the given namespace (typically globals()).

    Uses a module-level guard to ensure hooks are only registered once. When running
    from the monorepo root, both the root conftest.py and per-project conftest.py files
    are discovered by pytest. Without the guard, pytest_addoption would fail with
    duplicate option errors.

    The first conftest.py to call this function gets the hooks. Subsequent calls are no-ops.
    """
    global _registered
    if _registered:
        return
    _registered = True

    namespace["pytest_sessionstart"] = _pytest_sessionstart
    namespace["pytest_sessionfinish"] = _pytest_sessionfinish
    namespace["pytest_addoption"] = _pytest_addoption
    namespace["pytest_load_initial_conftests"] = _pytest_load_initial_conftests
    namespace["pytest_configure"] = _pytest_configure
    namespace["pytest_terminal_summary"] = _pytest_terminal_summary
