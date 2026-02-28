"""Resource guard system for enforcing pytest marks on external tool usage.

Provides PATH wrapper scripts that intercept calls to guarded binaries (tmux,
rsync, unison) during tests. During the test call phase, wrappers:
- Block invocation if the test lacks the corresponding mark (catches missing marks)
- Track invocation if the test has the mark (catches superfluous marks)

Docker and Modal use Python SDKs (not CLI binaries), so they are not guarded here.

Usage:
    Call create_resource_guard_wrappers() during pytest_sessionstart and
    cleanup_resource_guard_wrappers() during pytest_sessionfinish. Register the
    three runtest hooks (pytest_runtest_setup, pytest_runtest_teardown,
    pytest_runtest_makereport) into the conftest namespace.
"""

import os
import shutil
import stat
import tempfile
from collections.abc import Generator
from pathlib import Path
from typing import Final

import pytest

# Resources guarded by PATH wrapper scripts. Each resource name corresponds to
# both a binary on PATH and a pytest mark name (e.g., @pytest.mark.tmux).
GUARDED_RESOURCES: Final[list[str]] = ["tmux", "rsync", "unison"]


class MissingGuardedResourceError(Exception):
    """A guarded resource binary (tmux, rsync, unison) is not installed."""


# Module-level state for resource guard wrappers. The wrapper directory is created
# once per session (by the controller or single process) and reused by xdist workers.
# _owns_guard_wrapper_dir tracks whether this process created the directory (and is
# therefore responsible for deleting it) vs merely reusing one inherited from a parent
# process via the _PYTEST_GUARD_WRAPPER_DIR env var.
_guard_wrapper_dir: str | None = None
_owns_guard_wrapper_dir: bool = False


def generate_wrapper_script(resource: str, real_path: str) -> str:
    """Generate a bash wrapper script for a guarded resource.

    The wrapper checks environment variables set by the pytest_runtest_call hook:
    - _PYTEST_GUARD_PHASE: Only enforce during the "call" phase (not setup/teardown)
    - _PYTEST_GUARD_<RESOURCE>: "block" if the test lacks the mark, "allow" if it has it
    - _PYTEST_GUARD_TRACKING_DIR: Directory where tracking files are created

    During the call phase:
    - If the guard is "block", the wrapper prints an error and exits 127
    - If the guard is "allow", the wrapper touches a tracking file and delegates
    Outside the call phase (fixture setup/teardown), the wrapper always delegates.
    """
    bash_guard_var = f"$_PYTEST_GUARD_{resource.upper()}"
    return f"""#!/bin/bash
if [ "$_PYTEST_GUARD_PHASE" = "call" ]; then
    if [ "{bash_guard_var}" = "block" ]; then
        echo "RESOURCE GUARD: Test invoked '{resource}' without @pytest.mark.{resource} mark." >&2
        echo "Add @pytest.mark.{resource} to the test, or remove the {resource} usage." >&2
        exit 127
    fi
    if [ "{bash_guard_var}" = "allow" ] && [ -n "$_PYTEST_GUARD_TRACKING_DIR" ]; then
        touch "$_PYTEST_GUARD_TRACKING_DIR/{resource}"
    fi
fi
exec "{real_path}" "$@"
"""


def create_resource_guard_wrappers() -> None:
    """Create wrapper scripts for guarded resources and prepend to PATH.

    Each wrapper intercepts calls to the corresponding binary and enforces
    that the test has the appropriate pytest mark.

    For xdist: the controller creates the wrappers and modifies PATH. Workers
    inherit the modified PATH and wrapper directory via environment variables.
    The _PYTEST_GUARD_WRAPPER_DIR env var signals that wrappers already exist.
    """
    global _guard_wrapper_dir, _owns_guard_wrapper_dir

    # If wrappers already exist (e.g., inherited from xdist controller), reuse them.
    existing_dir = os.environ.get("_PYTEST_GUARD_WRAPPER_DIR")
    if existing_dir and Path(existing_dir).is_dir():
        _guard_wrapper_dir = existing_dir
        _owns_guard_wrapper_dir = False
        return

    original_path = os.environ.get("PATH", "")
    os.environ["_PYTEST_GUARD_ORIGINAL_PATH"] = original_path

    _guard_wrapper_dir = tempfile.mkdtemp(prefix="pytest_resource_guards_")
    _owns_guard_wrapper_dir = True

    for resource in GUARDED_RESOURCES:
        real_path = shutil.which(resource)
        if real_path is None:
            raise MissingGuardedResourceError(
                f"Guarded resource '{resource}' not found on PATH. "
                f"Install {resource} or remove it from GUARDED_RESOURCES."
            )

        wrapper_path = Path(_guard_wrapper_dir) / resource
        wrapper_path.write_text(generate_wrapper_script(resource, real_path))
        wrapper_path.chmod(wrapper_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    # Prepend wrapper directory to PATH and store for xdist workers
    os.environ["PATH"] = f"{_guard_wrapper_dir}{os.pathsep}{original_path}"
    os.environ["_PYTEST_GUARD_WRAPPER_DIR"] = _guard_wrapper_dir


def cleanup_resource_guard_wrappers() -> None:
    """Remove wrapper scripts and restore PATH.

    Only the process that created the wrappers should delete them.  Processes
    that merely reused an existing wrapper directory (e.g. xdist workers) just
    clear their local reference.
    """
    global _guard_wrapper_dir, _owns_guard_wrapper_dir

    if not _owns_guard_wrapper_dir:
        _guard_wrapper_dir = None
        return

    if _guard_wrapper_dir is not None:
        # Restore original PATH
        original_path = os.environ.get("_PYTEST_GUARD_ORIGINAL_PATH")
        if original_path is not None:
            os.environ["PATH"] = original_path

        shutil.rmtree(_guard_wrapper_dir, ignore_errors=True)
        _guard_wrapper_dir = None

    _owns_guard_wrapper_dir = False

    # Clean up guard env vars
    for key in ("_PYTEST_GUARD_WRAPPER_DIR", "_PYTEST_GUARD_ORIGINAL_PATH"):
        os.environ.pop(key, None)


# ---------------------------------------------------------------------------
# Pytest hook implementations (prefixed with _ to avoid accidental discovery)
# ---------------------------------------------------------------------------


@pytest.hookimpl(hookwrapper=True)
def _pytest_runtest_setup(item: pytest.Item) -> Generator[None, None, None]:
    """Activate resource guards for the entire test lifecycle.

    Guards are active during setup, call, and teardown. If a test uses a
    resource (directly or via fixtures), it needs the corresponding mark.

    Setting vars early also ensures fixtures that snapshot os.environ
    (like get_subprocess_test_env) capture the guard configuration.
    """
    if _guard_wrapper_dir is None:
        yield
        return

    marks = {m.name for m in item.iter_markers()}

    # Create per-test tracking directory
    tracking_dir = tempfile.mkdtemp(prefix="pytest_guard_track_")
    setattr(item, "_resource_tracking_dir", tracking_dir)  # noqa: B010
    setattr(item, "_resource_marks", marks)  # noqa: B010

    for resource in GUARDED_RESOURCES:
        env_var = f"_PYTEST_GUARD_{resource.upper()}"
        if resource in marks:
            os.environ[env_var] = "allow"
        else:
            os.environ[env_var] = "block"

    os.environ["_PYTEST_GUARD_TRACKING_DIR"] = tracking_dir
    os.environ["_PYTEST_GUARD_PHASE"] = "call"

    yield


@pytest.hookimpl(hookwrapper=True)
def _pytest_runtest_teardown(item: pytest.Item) -> Generator[None, None, None]:
    """Clean up resource guard environment variables after teardown."""
    yield

    if _guard_wrapper_dir is None:
        return

    os.environ.pop("_PYTEST_GUARD_PHASE", None)
    os.environ.pop("_PYTEST_GUARD_TRACKING_DIR", None)
    for resource in GUARDED_RESOURCES:
        os.environ.pop(f"_PYTEST_GUARD_{resource.upper()}", None)


@pytest.hookimpl(hookwrapper=True)
def _pytest_runtest_makereport(
    item: pytest.Item,
    call: pytest.CallInfo,  # type: ignore[type-arg]
) -> Generator[None, None, None]:
    """Enforce that tests with resource marks actually invoked the resource.

    After the call phase completes successfully, checks each marked resource's
    tracking file. If a test has @pytest.mark.<resource> but the resource binary
    was never invoked during the test function, the test is failed.

    This catches superfluous marks that would unnecessarily slow down filtered
    test runs (e.g., `pytest -m 'not tmux'` skipping a test that doesn't use tmux).
    """
    outcome = yield
    report = outcome.get_result()

    # Only check after the call phase, and only if the test passed
    if call.when != "call" or not report.passed:
        # Clean up tracking dir on the final phase (teardown)
        if call.when == "teardown":
            tracking_dir = getattr(item, "_resource_tracking_dir", None)
            if tracking_dir:
                shutil.rmtree(tracking_dir, ignore_errors=True)
        return

    tracking_dir = getattr(item, "_resource_tracking_dir", None)
    if tracking_dir is None:
        return

    marks: set[str] = getattr(item, "_resource_marks", set())

    for resource in GUARDED_RESOURCES:
        if resource not in marks:
            continue
        tracking_file = Path(tracking_dir) / resource
        if not tracking_file.exists():
            report.outcome = "failed"
            report.longrepr = (
                f"Test marked with @pytest.mark.{resource} but never invoked {resource}.\n"
                f"Remove the mark or ensure the test exercises {resource}."
            )
            break
