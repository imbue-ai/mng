"""Shared pytest fixtures for mngr tests."""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Generator
from typing import NamedTuple
from uuid import uuid4

import pluggy
import psutil
import pytest
from click.testing import CliRunner
from urwid.widget.listbox import SimpleFocusListWalker

import imbue.mngr.main
from imbue.mngr.agents.agent_registry import load_agents_from_plugins
from imbue.mngr.config.data_types import MngrConfig
from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.plugins import hookspecs
from imbue.mngr.primitives import ProviderInstanceName
from imbue.mngr.providers.local.instance import LocalProviderInstance
from imbue.mngr.providers.modal.backend import ModalProviderBackend
from imbue.mngr.providers.modal.instance import ModalProviderInstance
from imbue.mngr.providers.registry import load_local_backend_only
from imbue.mngr.providers.registry import reset_backend_registry
from imbue.mngr.utils.testing import get_subprocess_test_env

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


# Track test IDs used by this worker/process for cleanup verification.
# Each xdist worker is a separate process with isolated memory, so this
# list only contains IDs from tests run by THIS worker.
_worker_test_ids: list[str] = []


@pytest.fixture
def mngr_test_id() -> str:
    """Generate a unique test ID for isolation.

    This ID is used for both the host directory and prefix to ensure
    test isolation and easy cleanup of test resources (e.g., tmux sessions).
    """
    test_id = uuid4().hex
    _worker_test_ids.append(test_id)
    return test_id


@pytest.fixture
def mngr_test_prefix(mngr_test_id: str) -> str:
    """Get the test prefix for tmux session names.

    Format: mngr_{test_id}- (underscore separator for easy cleanup).
    """
    return f"mngr_{mngr_test_id}-"


@pytest.fixture
def mngr_test_root_name(mngr_test_id: str) -> str:
    """Get the test root name for config isolation.

    Format: mngr-test-{test_id}

    This ensures tests don't load the project's .mngr/settings.toml config,
    which might have settings like add_command that would interfere with tests.
    """
    return f"mngr-test-{mngr_test_id}"


@pytest.fixture(autouse=True)
def setup_test_mngr_env(
    temp_host_dir: Path,
    mngr_test_prefix: str,
    mngr_test_root_name: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Set up mngr environment variables for all tests.

    This autouse fixture ensures:
    - MNGR_HOST_DIR points to a temporary directory (not ~/.mngr)
    - MNGR_PREFIX uses a unique test ID for isolation
    - MNGR_ROOT_NAME prevents loading project config (.mngr/settings.toml)
    """
    monkeypatch.setenv("MNGR_HOST_DIR", str(temp_host_dir))
    monkeypatch.setenv("MNGR_PREFIX", mngr_test_prefix)
    monkeypatch.setenv("MNGR_ROOT_NAME", mngr_test_root_name)


@pytest.fixture
def temp_host_dir(tmp_path: Path) -> Path:
    """Create a temporary directory for host/mngr data.

    This fixture ensures tests don't write to ~/.mngr.
    """
    host_dir = tmp_path / "mngr"
    host_dir.mkdir()
    return host_dir


@pytest.fixture
def temp_work_dir(tmp_path: Path) -> Path:
    """Create a temporary work_dir directory for agents."""
    work_dir = tmp_path / "work_dir"
    work_dir.mkdir()
    return work_dir


@pytest.fixture
def temp_config(temp_host_dir: Path, mngr_test_prefix: str) -> MngrConfig:
    """Create a MngrConfig with a temporary host directory.

    Use this fixture when calling API functions that need a config.
    """
    return MngrConfig(default_host_dir=temp_host_dir, prefix=mngr_test_prefix)


@pytest.fixture
def temp_mngr_ctx(temp_config: MngrConfig, plugin_manager: pluggy.PluginManager) -> MngrContext:
    """Create a MngrContext with a temporary host directory.

    Use this fixture when calling API functions that need a context.
    """
    return MngrContext(config=temp_config, pm=plugin_manager)


@pytest.fixture
def local_provider(temp_host_dir: Path, temp_mngr_ctx: MngrContext) -> LocalProviderInstance:
    """Create a LocalProviderInstance with a temporary host directory."""
    return LocalProviderInstance(
        name=ProviderInstanceName("local"),
        host_dir=temp_host_dir,
        mngr_ctx=temp_mngr_ctx,
    )


@pytest.fixture
def cli_runner() -> CliRunner:
    """Create a Click CLI runner for testing CLI commands."""
    return CliRunner()


@pytest.fixture(autouse=True)
def plugin_manager() -> Generator[pluggy.PluginManager, None, None]:
    """Create a plugin manager with mngr hookspecs and local backend only.

    This fixture only loads the local provider backend, not modal. This ensures
    tests don't depend on Modal credentials being available.

    Also loads external plugins via setuptools entry points to match the behavior
    of load_config(). This ensures that external plugins like mngr_opencode are
    discovered and registered.

    This fixture also resets the module-level plugin manager singleton to ensure
    test isolation.
    """
    # Reset the module-level plugin manager singleton before each test
    imbue.mngr.main.reset_plugin_manager()

    # Clear the backend registry to ensure clean state
    reset_backend_registry()

    pm = pluggy.PluginManager("mngr")
    pm.add_hookspecs(hookspecs)
    pm.load_setuptools_entrypoints("mngr")

    # Only register the local backend, not modal
    # This prevents tests from depending on Modal credentials
    # This also loads the provider configs since backends and configs are registered together
    load_local_backend_only(pm)

    # Load other registries (agents)
    load_agents_from_plugins(pm)

    yield pm

    # Reset after the test as well
    imbue.mngr.main.reset_plugin_manager()
    reset_backend_registry()

    # Clean up Modal app contexts and sandbox cache to prevent async cleanup errors
    # and ensure test isolation
    ModalProviderBackend.reset_app_registry()
    ModalProviderInstance.reset_sandbox_cache()


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
    """Kill the specified tmux sessions."""
    for session in sessions:
        try:
            subprocess.run(
                ["tmux", "kill-session", "-t", session],
                capture_output=True,
                timeout=5,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
            pass


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


# Track Modal app names that were created during tests for cleanup verification.
# This enables detection of leaked apps that weren't properly cleaned up.
_worker_modal_app_names: list[str] = []


def register_modal_test_app(app_name: str) -> None:
    """Register a Modal app name for cleanup verification.

    Call this when creating a Modal app during tests to enable leak detection.
    The app_name should match the name used when creating the Modal app.
    """
    if app_name not in _worker_modal_app_names:
        _worker_modal_app_names.append(app_name)


# Track Modal volume names that were created during tests for cleanup verification.
# This enables detection of leaked volumes that weren't properly cleaned up.
# Unlike Modal Apps, volumes are global to the account (not app-specific), so they
# must be tracked and cleaned up separately.
_worker_modal_volume_names: list[str] = []


def register_modal_test_volume(volume_name: str) -> None:
    """Register a Modal volume name for cleanup verification.

    Call this when creating a Modal volume during tests to enable leak detection.
    The volume_name should match the name used when creating the Modal volume.
    """
    if volume_name not in _worker_modal_volume_names:
        _worker_modal_volume_names.append(volume_name)


# Track Modal environment names that were created during tests for cleanup verification.
# This enables detection of leaked environments that weren't properly cleaned up.
# Modal environments are used to scope all resources (apps, volumes, sandboxes) to a
# specific user.
_worker_modal_environment_names: list[str] = []


def register_modal_test_environment(environment_name: str) -> None:
    """Register a Modal environment name for cleanup verification.

    Call this when creating a Modal environment during tests to enable leak detection.
    The environment_name should match the name used when creating resources in that environment.
    """
    if environment_name not in _worker_modal_environment_names:
        _worker_modal_environment_names.append(environment_name)


# =============================================================================
# Modal subprocess test environment fixture
# =============================================================================


class ModalSubprocessTestEnv(NamedTuple):
    """Environment configuration for Modal subprocess tests."""

    env: dict[str, str]
    prefix: str
    host_dir: Path


@pytest.fixture
def modal_subprocess_env(
    tmp_path: Path,
    mngr_test_id: str,
) -> Generator[ModalSubprocessTestEnv, None, None]:
    """Create a subprocess test environment with unique prefix for Modal tests.

    This fixture:
    1. Creates a unique MNGR_PREFIX so each test gets its own Modal environment
    2. Creates a unique MNGR_HOST_DIR so each test gets its own user_id file
    3. Cleans up the Modal environment after the test completes

    This ensures Modal environments don't leak between tests.
    """
    prefix = f"mngr_{mngr_test_id}-"
    host_dir = tmp_path / "mngr"
    host_dir.mkdir()

    env = get_subprocess_test_env(
        root_name="mngr-acceptance-test",
        prefix=prefix,
        host_dir=host_dir,
    )

    yield ModalSubprocessTestEnv(env=env, prefix=prefix, host_dir=host_dir)

    # Clean up Modal environment after the test.
    # The environment name is {prefix}{user_id}, but since we used a unique host_dir,
    # the user_id was just created for this test. We need to read it to get the full name.
    user_id_file = host_dir / "user_id"
    if user_id_file.exists():
        user_id = user_id_file.read_text().strip()
        environment_name = f"{prefix}{user_id}"

        # Truncate environment_name if needed (Modal has 64 char limit)
        if len(environment_name) > 64:
            environment_name = environment_name[:64]

        # Delete the environment (this also cleans up any remaining resources in it)
        try:
            subprocess.run(
                ["uv", "run", "modal", "environment", "delete", environment_name, "--yes"],
                capture_output=True,
                timeout=30,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
            pass


def _get_leaked_modal_apps() -> list[tuple[str, str]]:
    """Get Modal apps that were registered and are still running.

    Returns a list of (app_id, app_name) tuples for apps that were created during
    tests but are still running (not in 'stopped' state).

    Uses 'uv run modal app list --json' to query the current state of all apps.
    """
    if not _worker_modal_app_names:
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
            if app_name in _worker_modal_app_names and state != "stopped":
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
    if not _worker_modal_volume_names:
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
            if volume_name in _worker_modal_volume_names:
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
    if not _worker_modal_environment_names:
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
            if env_name in _worker_modal_environment_names:
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

    # 2. Check for leftover tmux sessions from this worker's tests
    leftover_sessions: list[str] = []
    for test_id in _worker_test_ids:
        prefix = f"mngr_{test_id}-"
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
            "TEST SESSION CLEANUP FOUND LEAKED RESOURCES!\n"
            "=" * 70 + "\n\n" + "\n\n".join(errors) + "\n\n"
            "These resources have been cleaned up, but tests should not leak!\n"
            "Please fix the test(s) that failed to clean up properly."
        )
