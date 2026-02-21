import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Generator

import pluggy
import psutil
import pytest
import toml
from urwid.widget.listbox import SimpleFocusListWalker

import imbue.mng.main
from imbue.mng.agents.agent_registry import load_agents_from_plugins
from imbue.mng.agents.agent_registry import reset_agent_registry
from imbue.mng.fixtures import worker_modal_app_names
from imbue.mng.fixtures import worker_modal_environment_names
from imbue.mng.fixtures import worker_modal_volume_names
from imbue.mng.fixtures import worker_test_ids
from imbue.mng.plugins import hookspecs
from imbue.mng.providers.modal.backend import ModalProviderBackend
from imbue.mng.providers.registry import load_local_backend_only
from imbue.mng.providers.registry import reset_backend_registry
from imbue.mng.utils.testing import assert_home_is_temp_directory
from imbue.mng.utils.testing import cleanup_tmux_session

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


@pytest.fixture
def _isolate_tmux_server(
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[None, None, None]:
    """Give each test its own isolated tmux server.

    This fixture:
    - Creates a per-test TMUX_TMPDIR under /tmp so each test gets its own
      tmux server socket, preventing xdist workers from racing on the shared
      default tmux server.
    - Unsets TMUX so tmux commands connect to the isolated server (via
      TMUX_TMPDIR) rather than the real server.
    - On teardown, kills the isolated tmux server and cleans up the tmpdir.

    IMPORTANT: We use /tmp directly instead of pytest's tmp_path because
    tmux sockets are Unix domain sockets, which have a ~104-byte path
    length limit on macOS. Pytest's tmp_path lives under
    /private/var/folders/.../pytest-of-.../... which is already ~80+ bytes,
    leaving no room for tmux's tmux-$UID/default suffix. When the path
    exceeds the limit, tmux silently falls back to the default socket,
    defeating isolation entirely (and potentially killing production
    tmux servers during test cleanup).
    """
    tmux_tmpdir = Path(tempfile.mkdtemp(prefix="mng-tmux-", dir="/tmp"))
    monkeypatch.setenv("TMUX_TMPDIR", str(tmux_tmpdir))
    # Unset TMUX so tmux commands during the test connect to the isolated
    # server (via TMUX_TMPDIR) rather than the real server. When TMUX is
    # set (because we're running inside a tmux session), tmux uses it to
    # find the current server, overriding TMUX_TMPDIR.
    monkeypatch.delenv("TMUX", raising=False)

    yield

    # Kill the test's isolated tmux server to clean up any leaked sessions
    # or processes. We must use -S with the explicit socket path because:
    # 1. The TMUX env var (set when running inside tmux) tells tmux to
    #    connect to the CURRENT server, overriding TMUX_TMPDIR entirely.
    #    Without -S, kill-server would kill the real tmux server.
    # 2. We also unset TMUX in the env as a belt-and-suspenders measure.
    tmux_tmpdir_str = str(tmux_tmpdir)
    assert tmux_tmpdir_str.startswith("/tmp/mng-tmux-"), (
        f"TMUX_TMPDIR safety check failed! Expected /tmp/mng-tmux-* path but got: {tmux_tmpdir_str}. "
        "Refusing to run 'tmux kill-server' to avoid killing the real tmux server."
    )
    socket_path = Path(tmux_tmpdir_str) / f"tmux-{os.getuid()}" / "default"
    kill_env = os.environ.copy()
    kill_env.pop("TMUX", None)
    kill_env["TMUX_TMPDIR"] = tmux_tmpdir_str
    subprocess.run(
        ["tmux", "-S", str(socket_path), "kill-server"],
        capture_output=True,
        env=kill_env,
    )

    # Clean up the tmpdir we created outside of pytest's tmp_path.
    shutil.rmtree(tmux_tmpdir, ignore_errors=True)


@pytest.fixture(autouse=True)
def setup_test_mng_env(
    tmp_home_dir: Path,
    temp_host_dir: Path,
    mng_test_prefix: str,
    mng_test_root_name: str,
    monkeypatch: pytest.MonkeyPatch,
    _isolate_tmux_server: None,
) -> Generator[None, None, None]:
    """Set up environment variables for all tests.

    This autouse fixture ensures:
    - HOME points to tmp_path (not the real ~/)
    - MNG_HOST_DIR points to tmp_path/.mng (not ~/.mng)
    - MNG_PREFIX uses a unique test ID for isolation
    - MNG_ROOT_NAME prevents loading project config (.mng/settings.toml)
    - TMUX_TMPDIR gives each test its own tmux server (via _isolate_tmux_server)

    By setting HOME to tmp_path, tests cannot accidentally read or modify
    files in the real home directory. This protects files like ~/.claude.json.
    """
    # before we nuke our home directory, we need to load the right token from the real home directory
    modal_toml_path = Path(os.path.expanduser("~/.modal.toml"))
    if modal_toml_path.exists():
        for value in toml.load(modal_toml_path).values():
            if value.get("active", ""):
                monkeypatch.setenv("MODAL_TOKEN_ID", value.get("token_id", ""))
                monkeypatch.setenv("MODAL_TOKEN_SECRET", value.get("token_secret", ""))
                break
    if not os.environ.get("MODAL_TOKEN_ID") or not os.environ.get("MODAL_TOKEN_SECRET"):
        # check if we have "release" mark enabled:
        if "release" in getattr(pytest, "current_test_marks", []):
            raise Exception(
                "No active Modal token found in ~/.modal.toml for release tests. Please ensure you have an active token configured or set the env vars"
            )

    monkeypatch.setenv("HOME", str(tmp_home_dir))
    monkeypatch.setenv("MNG_HOST_DIR", str(temp_host_dir))
    monkeypatch.setenv("MNG_PREFIX", mng_test_prefix)
    monkeypatch.setenv("MNG_ROOT_NAME", mng_test_root_name)

    # Unison derives its config directory from $HOME. Since we override HOME
    # above, unison tries to create its config dir inside tmp_path, which
    # fails because the expected parent directories don't exist. The UNISON
    # env var overrides this to a path we control.
    unison_dir = tmp_home_dir / ".unison"
    unison_dir.mkdir(exist_ok=True)
    monkeypatch.setenv("UNISON", str(unison_dir))

    # Safety check: verify Path.home() is in a temp directory.
    # If this fails, tests could accidentally modify the real home directory.
    assert_home_is_temp_directory()

    yield


@pytest.fixture(autouse=True)
def plugin_manager() -> Generator[pluggy.PluginManager, None, None]:
    """Create a plugin manager with mng hookspecs and local backend only.

    This fixture only loads the local provider backend, not modal. This ensures
    tests don't depend on Modal credentials being available.

    Also loads external plugins via setuptools entry points to match the behavior
    of load_config(). This ensures that external plugins like mng_opencode are
    discovered and registered.

    This fixture also resets the module-level plugin manager singleton to ensure
    test isolation.
    """
    # Reset the module-level plugin manager singleton before each test
    imbue.mng.main.reset_plugin_manager()

    # Clear the registries to ensure clean state
    reset_backend_registry()
    reset_agent_registry()

    pm = pluggy.PluginManager("mng")
    pm.add_hookspecs(hookspecs)
    pm.load_setuptools_entrypoints("mng")

    # Only register the local backend, not modal
    # This prevents tests from depending on Modal credentials
    # This also loads the provider configs since backends and configs are registered together
    load_local_backend_only(pm)

    # Load other registries (agents)
    load_agents_from_plugins(pm)

    yield pm

    # Reset after the test as well
    imbue.mng.main.reset_plugin_manager()
    reset_backend_registry()
    reset_agent_registry()

    # Clean up Modal app contexts to prevent async cleanup errors
    ModalProviderBackend.reset_app_registry()


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
