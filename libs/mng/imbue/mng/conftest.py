import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Generator
from uuid import uuid4

import psutil
import pytest
from urwid.widget.listbox import SimpleFocusListWalker

from imbue.mng.primitives import UserId
from imbue.mng.providers.modal.backend import ModalProviderBackend
from imbue.mng.testing import ModalSubprocessTestEnv
from imbue.mng.testing import cleanup_tmux_session
from imbue.mng.testing import delete_modal_apps_in_environment
from imbue.mng.testing import delete_modal_environment
from imbue.mng.testing import delete_modal_volumes_in_environment
from imbue.mng.testing import generate_test_environment_name
from imbue.mng.testing import get_subprocess_test_env
from imbue.mng.testing import worker_modal_app_names
from imbue.mng.testing import worker_modal_environment_names
from imbue.mng.testing import worker_modal_volume_names
from imbue.mng.testing import worker_test_ids
from imbue.mng.utils.plugin_testing import register_plugin_test_fixtures

# Register the standard shared fixtures (cg, cli_runner, plugin_manager,
# temp_host_dir, temp_mng_ctx, local_provider, setup_git_config, etc.)
register_plugin_test_fixtures(globals())

# The urwid import above triggers creation of deprecated module aliases.
# These are the deprecated module aliases that urwid 3.x creates for backwards
# compatibility. They point to the new locations but emit DeprecationWarning
# when any attribute (including __file__) is accessed. By removing them from
# sys.modules, we prevent warnings during pytest/inspect module iteration.
_URWID_DEPRECATED_ALIASES = (
    "urwid.web_display",
    "urwid.lcd_display",
    "urwid.html_fragment",
    "urwid.monitored_list",
    "urwid.listbox",
    "urwid.treetools",
)


def _remove_deprecated_urwid_module_aliases() -> None:
    """Remove deprecated urwid module aliases from sys.modules.

    urwid 3.x maintains backwards compatibility by creating deprecated module
    aliases (e.g., urwid.listbox -> urwid.widget.listbox). These aliases emit
    DeprecationWarning when any attribute is accessed, including __file__.

    When pytest/Python's inspect module iterates over sys.modules during test
    collection, it accesses __file__ on these deprecated aliases, triggering
    many spurious warnings. By removing the aliases from sys.modules after
    urwid is imported, we prevent these warnings without suppressing them.

    This is not suppression - we're removing the problematic module objects
    rather than ignoring warnings they emit.
    """
    for mod in _URWID_DEPRECATED_ALIASES:
        if mod in sys.modules:
            del sys.modules[mod]


# Clean up deprecated urwid aliases immediately after import.
# This needs to happen at module load time, before pytest starts collecting tests.
# We use SimpleFocusListWalker to ensure urwid is fully loaded first.
_ = SimpleFocusListWalker
_remove_deprecated_urwid_module_aliases()


# =============================================================================
# mng-specific fixtures (not shared via register_plugin_test_fixtures)
# =============================================================================


@pytest.fixture
def temp_work_dir(tmp_path: Path) -> Path:
    """Create a temporary work_dir directory for agents."""
    work_dir = tmp_path / "work_dir"
    work_dir.mkdir()
    return work_dir


@pytest.fixture
def project_config_dir(temp_git_repo: Path, mng_test_root_name: str) -> Path:
    """Return the project config directory inside the test git repo, creating it.

    The directory is named `.{mng_test_root_name}` (e.g., `.mng-test-abc123`).
    Tests can write `settings.toml` or `settings.local.toml` into this directory
    to configure project-level settings for a test.
    """
    config_dir = temp_git_repo / f".{mng_test_root_name}"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


@pytest.fixture
def temp_git_repo_cwd(temp_git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create a temporary git repository and chdir into it.

    Combines temp_git_repo with monkeypatch.chdir so tests that need a git
    repo as the working directory (e.g. for project-scope config discovery)
    don't need to request both fixtures separately.
    """
    monkeypatch.chdir(temp_git_repo)
    return temp_git_repo


@pytest.fixture
def per_host_dir(temp_host_dir: Path) -> Path:
    """Get the host directory for the local provider.

    This is the directory where host-scoped data lives: agents/, data.json,
    activity/, etc. This is the same as temp_host_dir (e.g. ~/.mng/).
    """
    return temp_host_dir


# =============================================================================
# Modal-specific autouse fixture
# =============================================================================


@pytest.fixture(autouse=True)
def _reset_modal_app_registry() -> Generator[None, None, None]:
    """Clean up Modal app contexts after each test to prevent async cleanup errors."""
    yield
    ModalProviderBackend.reset_app_registry()


# =============================================================================
# Modal subprocess test environment fixtures (session-scoped)
# =============================================================================


@pytest.fixture(scope="session")
def modal_test_session_env_name() -> str:
    """Generate a unique, timestamp-based environment name for this test session.

    This fixture is session-scoped, so all tests in a session share the same
    environment name. The name includes a UTC timestamp in the format:
    mng_test-YYYY-MM-DD-HH-MM-SS
    """
    return generate_test_environment_name()


@pytest.fixture(scope="session")
def modal_test_session_host_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Create a session-scoped host directory for Modal tests.

    This ensures all tests in a session share the same host directory,
    which means they share the same Modal environment.
    """
    host_dir = tmp_path_factory.mktemp("modal_session") / "mng"
    host_dir.mkdir(parents=True, exist_ok=True)
    return host_dir


@pytest.fixture(scope="session")
def modal_test_session_user_id() -> UserId:
    """Generate a deterministic user ID for the test session.

    This user ID is shared across all subprocess Modal tests in a session
    via the MNG_USER_ID environment variable. By generating it upfront,
    the cleanup fixture can construct the exact environment name without
    needing to find the user_id file in the profile directory structure.
    """
    return UserId(uuid4().hex)


@pytest.fixture(scope="session")
def modal_test_session_cleanup(
    modal_test_session_env_name: str,
    modal_test_session_user_id: UserId,
) -> Generator[None, None, None]:
    """Session-scoped fixture that cleans up the Modal environment at session end.

    This fixture ensures the Modal environment created for tests is deleted
    when the test session completes, including all apps and volumes.
    """
    yield

    # Clean up Modal environment after the session.
    # The environment name is {prefix}{user_id}, where prefix is based on the timestamp
    # and user_id is the session-scoped deterministic ID.
    prefix = f"{modal_test_session_env_name}-"
    environment_name = f"{prefix}{modal_test_session_user_id}"

    # Truncate environment_name if needed (Modal has 64 char limit)
    if len(environment_name) > 64:
        environment_name = environment_name[:64]

    # Delete apps, volumes, and environment using functions from testing.py
    delete_modal_apps_in_environment(environment_name)
    delete_modal_volumes_in_environment(environment_name)
    delete_modal_environment(environment_name)


@pytest.fixture
def modal_subprocess_env(
    modal_test_session_env_name: str,
    modal_test_session_host_dir: Path,
    modal_test_session_cleanup: None,
    modal_test_session_user_id: UserId,
) -> Generator[ModalSubprocessTestEnv, None, None]:
    """Create a subprocess test environment with session-scoped Modal environment.

    This fixture:
    1. Uses a session-scoped MNG_PREFIX based on UTC timestamp (mng_test-YYYY-MM-DD-HH-MM-SS)
    2. Uses a session-scoped MNG_HOST_DIR so all tests share the same host directory
    3. Sets MNG_USER_ID so all subprocesses use the same deterministic user ID
    4. Cleans up the Modal environment at the end of the session (not per-test)

    Using session-scoped environments reduces the number of environments created
    and makes cleanup easier (environments have timestamps in their names).
    """
    prefix = f"{modal_test_session_env_name}-"
    host_dir = modal_test_session_host_dir

    env = get_subprocess_test_env(
        root_name="mng-acceptance-test",
        prefix=prefix,
        host_dir=host_dir,
    )
    # Set the user ID so all subprocesses use the same deterministic ID.
    # This ensures the cleanup fixture can construct the exact environment name.
    env["MNG_USER_ID"] = modal_test_session_user_id

    yield ModalSubprocessTestEnv(env=env, prefix=prefix, host_dir=host_dir)


# =============================================================================
# Session Cleanup - Detect and clean up leaked test resources
# =============================================================================


def _get_tmux_sessions_with_prefix(prefix: str) -> list[str]:
    """Get tmux sessions matching the given prefix."""
    try:
        result = subprocess.run(
            ["tmux", "list-sessions", "-F", "#{session_name}"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return []
        sessions = [s.strip() for s in result.stdout.splitlines() if s.strip()]
        return [s for s in sessions if s.startswith(prefix)]
    except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
        return []


def _kill_tmux_sessions(sessions: list[str]) -> None:
    """Kill the specified tmux sessions and all their processes."""
    for session in sessions:
        cleanup_tmux_session(session)


def _is_xdist_worker_process(proc: psutil.Process) -> bool:
    """Check if a process is a pytest-xdist worker process."""
    try:
        cmdline = proc.cmdline()
        cmdline_str = " ".join(cmdline)
        # xdist workers are python processes running pytest with gw* identifiers
        return "pytest" in cmdline_str.lower() and "gw" in cmdline_str
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return False


def _format_process_info(proc: psutil.Process) -> str:
    """Format process information for error messages."""
    try:
        cmdline = proc.cmdline()[:5]
        return f"  PID {proc.pid}: {proc.name()} - {' '.join(cmdline)}"
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return f"  PID {proc.pid}: <process info unavailable>"


def _is_alive_non_zombie(proc: psutil.Process) -> bool:
    """Check if a process is alive and not a zombie."""
    try:
        return proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return False


def _get_leaked_modal_apps() -> list[tuple[str, str]]:
    """Get Modal apps that were registered and are still running.

    Returns a list of (app_id, app_name) tuples for apps that were created during
    tests but are still running (not in 'stopped' state).

    Uses 'uv run modal app list --json' to query the current state of all apps.
    """
    if not worker_modal_app_names:
        return []

    try:
        result = subprocess.run(
            ["uv", "run", "modal", "app", "list", "--json"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return []

        apps = json.loads(result.stdout)
        leaked: list[tuple[str, str]] = []

        for app in apps:
            app_name = app.get("Description", "")
            app_id = app.get("App ID", "")
            state = app.get("State", "")

            # Check if this app was created by our tests and is not stopped
            if app_name in worker_modal_app_names and state != "stopped":
                leaked.append((app_id, app_name))

        return leaked
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        return []


def _stop_modal_apps(apps: list[tuple[str, str]]) -> None:
    """Stop the specified Modal apps.

    Takes a list of (app_id, app_name) tuples and stops each app using
    'uv run modal app stop <app_id>'.

    This function is defensive and will silently skip any apps that cannot
    be stopped.
    """
    if not apps:
        return

    for app_id, _app_name in apps:
        try:
            subprocess.run(
                ["uv", "run", "modal", "app", "stop", app_id],
                capture_output=True,
                timeout=30,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
            pass


def _get_leaked_modal_volumes() -> list[str]:
    """Get Modal volumes that were registered and still exist.

    Returns a list of volume names for volumes that were created during
    tests and still exist (not yet deleted).

    Uses 'uv run modal volume list --json' to query the current state of all volumes.
    """
    if not worker_modal_volume_names:
        return []

    try:
        result = subprocess.run(
            ["uv", "run", "modal", "volume", "list", "--json"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return []

        volumes = json.loads(result.stdout)
        leaked: list[str] = []

        for volume in volumes:
            volume_name = volume.get("Name", "")

            # Check if this volume was created by our tests
            if volume_name in worker_modal_volume_names:
                leaked.append(volume_name)

        return leaked
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        return []


def _delete_modal_volumes(volume_names: list[str]) -> None:
    """Delete the specified Modal volumes.

    Takes a list of volume names and deletes each volume using
    'uv run modal volume delete <volume_name> --yes'.

    This function is defensive and will silently skip any volumes that cannot
    be deleted.
    """
    if not volume_names:
        return

    for volume_name in volume_names:
        try:
            subprocess.run(
                ["uv", "run", "modal", "volume", "delete", volume_name, "--yes"],
                capture_output=True,
                timeout=30,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
            pass


def _get_leaked_modal_environments() -> list[str]:
    """Get Modal environments that were registered and still exist.

    Returns a list of environment names for environments that were created during
    tests and still exist (not yet deleted).

    Uses 'uv run modal environment list --json' to query the current state of all environments.
    """
    if not worker_modal_environment_names:
        return []

    try:
        result = subprocess.run(
            ["uv", "run", "modal", "environment", "list", "--json"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return []

        environments = json.loads(result.stdout)
        leaked: list[str] = []

        for env in environments:
            env_name = env.get("name", "")

            # Check if this environment was created by our tests
            if env_name in worker_modal_environment_names:
                leaked.append(env_name)

        return leaked
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        return []


def _delete_modal_environments(environment_names: list[str]) -> None:
    """Delete the specified Modal environments.

    Takes a list of environment names and deletes each environment using
    'uv run modal environment delete <environment_name> --yes'.

    This function is defensive and will silently skip any environments that cannot
    be deleted.
    """
    if not environment_names:
        return

    for env_name in environment_names:
        try:
            subprocess.run(
                ["uv", "run", "modal", "environment", "delete", env_name, "--yes"],
                capture_output=True,
                timeout=30,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
            pass


@pytest.fixture(scope="session", autouse=True)
def session_cleanup() -> Generator[None, None, None]:
    """Session-scoped fixture to detect and clean up leaked test resources.

    This fixture runs at the end of each pytest session (once per xdist worker)
    and checks for:
    1. Leftover child processes (excluding xdist workers on the leader)
    2. Leftover tmux sessions created by this worker's tests
    3. Leftover Modal apps created by this worker's tests
    4. Leftover Modal volumes created by this worker's tests
    5. Leftover Modal environments created by this worker's tests

    If any leaked resources are found:
    - An error is raised to fail the test suite
    - The resources are killed as a last-ditch cleanup measure

    Tests should always clean up after themselves! This is just a safety net.
    """
    # Run all tests first
    yield

    errors: list[str] = []

    # Determine our role in xdist (if using xdist)
    is_xdist_worker = os.environ.get("PYTEST_XDIST_WORKER") is not None
    is_xdist_leader = not is_xdist_worker and os.environ.get("PYTEST_XDIST_TESTRUNUID") is not None

    # 1. Check for leftover child processes
    try:
        current = psutil.Process()
        children = list(current.children(recursive=True))
    except psutil.NoSuchProcess:
        children = []

    # On the xdist leader, filter out xdist worker processes (they're expected)
    if is_xdist_leader:
        children = [c for c in children if not _is_xdist_worker_process(c)]

    # Filter out zombie/dead processes - they're not actually leaked
    leftover_processes = [p for p in children if _is_alive_non_zombie(p)]

    if leftover_processes:
        proc_info = [_format_process_info(p) for p in leftover_processes]
        errors.append(
            "Leftover child processes found!\n"
            "Tests should clean up spawned processes before completing.\n" + "\n".join(proc_info)
        )

    # 2. Check for leftover tmux sessions from this worker's tests.
    # Note: Each test gets its own tmux server via TMUX_TMPDIR, and the
    # per-test fixture kills that server on teardown. This check queries
    # the default tmux server as a fallback safety net -- it would only
    # catch leaks if a test somehow bypassed the per-test TMUX_TMPDIR.
    leftover_sessions: list[str] = []
    for test_id in worker_test_ids:
        prefix = f"mng_{test_id}-"
        sessions = _get_tmux_sessions_with_prefix(prefix)
        leftover_sessions.extend(sessions)

    if leftover_sessions:
        errors.append(
            "Leftover test tmux sessions found!\n"
            "Tests should destroy their agents/sessions before completing.\n"
            + "\n".join(f"  {s}" for s in leftover_sessions)
        )

    # 3. Check for leftover Modal apps from this worker's tests
    leftover_apps = _get_leaked_modal_apps()

    if leftover_apps:
        app_info = [f"  {app_id} ({app_name})" for app_id, app_name in leftover_apps]
        errors.append(
            "Leftover Modal apps found!\n"
            "Tests should destroy their Modal hosts before completing.\n" + "\n".join(app_info)
        )

    # 4. Check for leftover Modal volumes from this worker's tests
    leftover_volumes = _get_leaked_modal_volumes()

    if leftover_volumes:
        volume_info = [f"  {volume_name}" for volume_name in leftover_volumes]
        errors.append(
            "Leftover Modal volumes found!\n"
            "Tests should delete their Modal volumes before completing.\n" + "\n".join(volume_info)
        )

    # 5. Check for leftover Modal environments from this worker's tests
    leftover_environments = _get_leaked_modal_environments()

    if leftover_environments:
        env_info = [f"  {env_name}" for env_name in leftover_environments]
        errors.append(
            "Leftover Modal environments found!\n"
            "Tests should delete their Modal environments before completing.\n" + "\n".join(env_info)
        )

    # 6. Clean up leaked resources (last-ditch safety measure)
    for proc in leftover_processes:
        try:
            proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass

    _kill_tmux_sessions(leftover_sessions)
    _stop_modal_apps(leftover_apps)
    _delete_modal_volumes(leftover_volumes)
    _delete_modal_environments(leftover_environments)

    # 7. Fail the test suite if any issues were found
    if errors:
        raise AssertionError(
            "=" * 70 + "\n"
            "TEST SESSION CLEANUP FOUND LEAKED RESOURCES!\n" + "=" * 70 + "\n\n" + "\n\n".join(errors) + "\n\n"
            "These resources have been cleaned up, but tests should not leak!\n"
            "Please fix the test(s) that failed to clean up properly."
        )
