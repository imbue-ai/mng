import json
import os
import re
import shutil
import signal
import socket
import subprocess
from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from pathlib import Path
from typing import Final
from uuid import uuid4

import pluggy
import pytest
from loguru import logger

from imbue.mngr.config.data_types import MngrConfig
from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.config.data_types import PROFILES_DIRNAME
from imbue.mngr.primitives import ProviderInstanceName
from imbue.mngr.providers.local.instance import LocalProviderInstance
from imbue.mngr.utils.polling import wait_for

# Prefix used for test environments
MODAL_TEST_ENV_PREFIX: Final[str] = "mngr_test-"

# Pattern to match test environment names: mngr_test-YYYY-MM-DD-HH-MM-SS
# The name may have additional suffixes (like user_id)
MODAL_TEST_ENV_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^mngr_test-(\d{4})-(\d{2})-(\d{2})-(\d{2})-(\d{2})-(\d{2})"
)


def get_subprocess_test_env(
    root_name: str = "mngr-test",
    prefix: str | None = None,
    host_dir: Path | None = None,
) -> dict[str, str]:
    """Get environment variables for subprocess calls that prevent loading project config.

    Sets MNGR_ROOT_NAME to a value that doesn't have a corresponding config directory,
    preventing subprocess tests from picking up .mngr/settings.toml which might have
    settings like add_command that would interfere with tests.

    The root_name parameter defaults to "mngr-test" but can be set to a descriptive
    name for your test category (e.g., "mngr-acceptance-test", "mngr-release-test").

    The prefix parameter, if provided, sets MNGR_PREFIX to a unique value. This is
    important for Modal tests to ensure each test gets its own environment.

    The host_dir parameter, if provided, sets MNGR_HOST_DIR to a unique directory.
    This is important for isolating the user_id file between tests.

    Returns a copy of os.environ with the specified environment variables set.
    """
    env = os.environ.copy()
    env["MNGR_ROOT_NAME"] = root_name
    if prefix is not None:
        env["MNGR_PREFIX"] = prefix
    if host_dir is not None:
        env["MNGR_HOST_DIR"] = str(host_dir)
    return env


def _get_descendant_pids(pid: str) -> list[str]:
    """Recursively get all descendant PIDs of a given process.

    Note: This mirrors Host._get_all_descendant_pids in host.py but uses subprocess
    directly instead of host.execute_command, since this is used for test cleanup
    outside of Host (e.g., in fixtures and context managers). The Host version goes
    through pyinfra which supports both local and SSH execution.
    """
    descendants: list[str] = []
    result = subprocess.run(
        ["pgrep", "-P", pid],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0 and result.stdout.strip():
        for child_pid in result.stdout.strip().split("\n"):
            if child_pid:
                descendants.append(child_pid)
                descendants.extend(_get_descendant_pids(child_pid))
    return descendants


def cleanup_tmux_session(session_name: str) -> None:
    """Clean up a tmux session, all its processes, and any associated activity monitors.

    Note: This mirrors the kill logic in Host.stop_agents (host.py) but uses subprocess
    directly instead of host.execute_command. The Host version goes through pyinfra to
    support both local and SSH execution, while this version is used for test cleanup
    in fixtures and context managers that don't have a Host instance.

    This does a thorough cleanup:
    1. Collects all pane PIDs and their descendant process trees
    2. Sends SIGTERM to all collected processes
    3. Kills the tmux session itself
    4. Sends SIGKILL to any processes that survived
    5. Kills any orphaned activity monitors for this session
    """
    # Collect all pane PIDs and their descendants before killing the session.
    # Use -s to list panes across ALL windows in the session, not just the current window.
    all_pids: list[str] = []
    result = subprocess.run(
        ["tmux", "list-panes", "-s", "-t", session_name, "-F", "#{pane_pid}"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0 and result.stdout.strip():
        for pane_pid in result.stdout.strip().split("\n"):
            if pane_pid:
                all_pids.append(pane_pid)
                all_pids.extend(_get_descendant_pids(pane_pid))

    # SIGTERM all processes
    for pid in all_pids:
        try:
            os.kill(int(pid), signal.SIGTERM)
        except (ProcessLookupError, ValueError):
            pass

    # Kill the tmux session (sends SIGHUP to remaining pane processes)
    subprocess.run(
        ["tmux", "kill-session", "-t", session_name],
        capture_output=True,
    )

    # SIGKILL any survivors
    for pid in all_pids:
        try:
            os.kill(int(pid), signal.SIGKILL)
        except (ProcessLookupError, ValueError):
            pass

    # Kill any orphaned activity monitors for this session (started with nohup, detached)
    subprocess.run(
        ["pkill", "-9", "-f", f"list-panes -t {session_name}"],
        capture_output=True,
    )


@contextmanager
def tmux_session_cleanup(session_name: str) -> Generator[str, None, None]:
    """Context manager that cleans up a tmux session and all its processes on exit."""
    try:
        yield session_name
    finally:
        cleanup_tmux_session(session_name)


def capture_tmux_pane_contents(session_name: str) -> str:
    """Capture the contents of a tmux session's pane and return as a string."""
    result = subprocess.run(
        ["tmux", "capture-pane", "-t", session_name, "-p"],
        capture_output=True,
        text=True,
    )
    return result.stdout


def tmux_session_exists(session_name: str) -> bool:
    """Check if a tmux session exists."""
    result = subprocess.run(
        ["tmux", "has-session", "-t", session_name],
        capture_output=True,
    )
    return result.returncode == 0


def make_local_provider(
    host_dir: Path,
    config: MngrConfig,
    name: str = "local",
    profile_dir: Path | None = None,
) -> LocalProviderInstance:
    """Create a LocalProviderInstance with the given host_dir and config.

    If profile_dir is not provided, a new one is created. To share state between
    multiple provider instances, pass the same profile_dir to each call.
    """
    pm = pluggy.PluginManager("mngr")
    # Create a profile directory in the host_dir if not provided
    if profile_dir is None:
        profile_dir = host_dir / PROFILES_DIRNAME / uuid4().hex
    profile_dir.mkdir(parents=True, exist_ok=True)
    mngr_ctx = MngrContext(config=config, pm=pm, profile_dir=profile_dir)
    return LocalProviderInstance(
        name=ProviderInstanceName(name),
        host_dir=host_dir,
        mngr_ctx=mngr_ctx,
    )


def make_mngr_ctx(default_host_dir: Path, prefix: str) -> MngrContext:
    """Create a MngrContext with the given default_host_dir, prefix, and a basic plugin manager."""
    config = MngrConfig(default_host_dir=default_host_dir, prefix=prefix)
    pm = pluggy.PluginManager("mngr")
    # Create a profile directory in the default_host_dir
    profile_dir = default_host_dir / PROFILES_DIRNAME / uuid4().hex
    profile_dir.mkdir(parents=True, exist_ok=True)
    return MngrContext(config=config, pm=pm, profile_dir=profile_dir)


def get_short_random_string() -> str:
    return uuid4().hex[:8]


# =============================================================================
# Modal test environment cleanup utilities
# =============================================================================


def _parse_test_env_timestamp(env_name: str) -> datetime | None:
    """Parse the timestamp from a test environment name.

    Returns the datetime if the name matches the test environment pattern,
    otherwise returns None.
    """
    match = MODAL_TEST_ENV_PATTERN.match(env_name)
    if not match:
        return None

    year, month, day, hour, minute, second = match.groups()
    return datetime(
        int(year),
        int(month),
        int(day),
        int(hour),
        int(minute),
        int(second),
        tzinfo=timezone.utc,
    )


def list_modal_test_environments() -> list[str]:
    """List all Modal test environments.

    Returns a list of environment names that match the test environment pattern
    (mngr_test-YYYY-MM-DD-HH-MM-SS*).
    """
    try:
        result = subprocess.run(
            ["uv", "run", "modal", "environment", "list", "--json"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            logger.warning("Failed to list Modal environments: {}", result.stderr)
            return []

        environments = json.loads(result.stdout)
        test_envs: list[str] = []

        for env in environments:
            env_name = env.get("name", "")
            if env_name.startswith(MODAL_TEST_ENV_PREFIX):
                test_envs.append(env_name)

        return test_envs
    except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError, json.JSONDecodeError) as e:
        logger.warning("Error listing Modal environments: {}", e)
        return []


def find_old_test_environments(
    max_age: timedelta,
) -> list[str]:
    """Find Modal test environments older than the specified age.

    Returns a list of environment names that are older than max_age.
    The age is determined by parsing the timestamp from the environment name.
    """
    now = datetime.now(timezone.utc)
    cutoff = now - max_age
    old_envs: list[str] = []

    for env_name in list_modal_test_environments():
        timestamp = _parse_test_env_timestamp(env_name)
        if timestamp is not None and timestamp < cutoff:
            old_envs.append(env_name)

    return old_envs


def delete_modal_apps_in_environment(environment_name: str) -> None:
    """Delete all Modal apps in the specified environment.

    This is robust to concurrent deletion - failures result in warnings, not errors.
    """
    try:
        result = subprocess.run(
            ["uv", "run", "modal", "app", "list", "--env", environment_name, "--json"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            # Environment may not exist or may have been deleted concurrently
            logger.debug("Could not list apps in environment {}: {}", environment_name, result.stderr)
            return

        apps = json.loads(result.stdout)
        for app in apps:
            app_id = app.get("App ID", "")
            app_name = app.get("Description", "")
            if app_id:
                try:
                    subprocess.run(
                        ["uv", "run", "modal", "app", "stop", app_id],
                        capture_output=True,
                        timeout=30,
                    )
                    logger.debug("Stopped Modal app {} ({})", app_name, app_id)
                except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError) as e:
                    logger.warning("Failed to stop Modal app {} ({}): {}", app_name, app_id, e)
    except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError, json.JSONDecodeError) as e:
        logger.warning("Failed to list/delete Modal apps in environment {}: {}", environment_name, e)


def delete_modal_volumes_in_environment(environment_name: str) -> None:
    """Delete all Modal volumes in the specified environment.

    This is robust to concurrent deletion - failures result in warnings, not errors.
    """
    try:
        result = subprocess.run(
            ["uv", "run", "modal", "volume", "list", "--env", environment_name, "--json"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            # Environment may not exist or may have been deleted concurrently
            logger.debug("Could not list volumes in environment {}: {}", environment_name, result.stderr)
            return

        volumes = json.loads(result.stdout)
        for volume in volumes:
            volume_name = volume.get("Name", "")
            if volume_name:
                try:
                    subprocess.run(
                        ["uv", "run", "modal", "volume", "delete", volume_name, "--env", environment_name, "--yes"],
                        capture_output=True,
                        timeout=30,
                    )
                    logger.debug("Deleted Modal volume {} in environment {}", volume_name, environment_name)
                except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError) as e:
                    logger.warning(
                        "Failed to delete Modal volume {} in environment {}: {}", volume_name, environment_name, e
                    )
    except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError, json.JSONDecodeError) as e:
        logger.warning("Failed to list/delete Modal volumes in environment {}: {}", environment_name, e)


def delete_modal_environment(environment_name: str) -> None:
    """Delete a Modal environment.

    This is robust to concurrent deletion - failures result in warnings, not errors.
    """
    try:
        subprocess.run(
            ["uv", "run", "modal", "environment", "delete", environment_name, "--yes"],
            capture_output=True,
            timeout=30,
        )
        logger.debug("Deleted Modal environment {}", environment_name)
    except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError) as e:
        logger.warning("Failed to delete Modal environment {}: {}", environment_name, e)


def cleanup_old_modal_test_environments(
    max_age_hours: float = 1.0,
) -> int:
    """Clean up Modal test environments older than the specified age.

    This function finds all Modal test environments with names matching the pattern
    mngr_test-YYYY-MM-DD-HH-MM-SS*, parses the timestamp from the name, and deletes
    those that are older than max_age_hours.

    For each old environment, it:
    1. Stops all apps in the environment
    2. Deletes all volumes in the environment
    3. Deletes the environment itself

    This function is designed to be robust to concurrent deletion. Any failure to
    delete an environment, app, or volume results in a warning, not an error.
    This allows the cleanup to continue even if some resources were already deleted
    by another process.

    Returns the number of environments that were processed (attempted deletion).
    """
    max_age = timedelta(hours=max_age_hours)
    old_envs = find_old_test_environments(max_age)

    if not old_envs:
        logger.info("No old Modal test environments found (older than {} hours)", max_age_hours)
        return 0

    logger.info("Found {} old Modal test environments to clean up", len(old_envs))

    for env_name in old_envs:
        logger.info("Cleaning up old test environment: {}", env_name)

        # Delete all apps in the environment first
        delete_modal_apps_in_environment(env_name)

        # Then delete all volumes
        delete_modal_volumes_in_environment(env_name)

        # Finally delete the environment itself
        delete_modal_environment(env_name)

    return len(old_envs)


# =============================================================================
# SSH test utilities
# =============================================================================


def find_free_port() -> int:
    """Find a free port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def is_port_open(port: int) -> bool:
    """Check if a port is open and accepting connections."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1.0)
            s.connect(("127.0.0.1", port))
            return True
    except (OSError, socket.timeout):
        return False


def generate_ssh_keypair(base_path: Path) -> tuple[Path, Path]:
    """Generate an SSH keypair for testing.

    Returns (private_key_path, public_key_path) tuple.
    """
    key_dir = base_path / "ssh_keys"
    key_dir.mkdir()
    key_path = key_dir / "id_ed25519"
    subprocess.run(
        [
            "ssh-keygen",
            "-t",
            "ed25519",
            "-f",
            str(key_path),
            "-N",
            "",
            "-q",
        ],
        check=True,
    )
    return key_path, Path(f"{key_path}.pub")


@contextmanager
def local_sshd(
    authorized_keys_content: str,
    base_path: Path,
) -> Generator[tuple[int, Path], None, None]:
    """Start a local sshd instance for testing.

    Yields (port, host_key_path) tuple.
    """
    # Check if sshd is available
    sshd_path = shutil.which("sshd")
    if sshd_path is None:
        pytest.skip("sshd not found - install openssh-server")
    # Assert needed for type narrowing since pytest.skip is typed as NoReturn
    assert sshd_path is not None

    # Ensure ~/.ssh directory exists for pyinfra's known_hosts handling
    ssh_dir = Path.home() / ".ssh"
    ssh_dir.mkdir(exist_ok=True)

    port = find_free_port()

    sshd_dir = base_path / "sshd"
    sshd_dir.mkdir()

    # Create directories
    etc_dir = sshd_dir / "etc"
    run_dir = sshd_dir / "run"
    etc_dir.mkdir()
    run_dir.mkdir()

    # Generate host key
    host_key_path = etc_dir / "ssh_host_ed25519_key"
    subprocess.run(
        [
            "ssh-keygen",
            "-t",
            "ed25519",
            "-f",
            str(host_key_path),
            "-N",
            "",
            "-q",
        ],
        check=True,
    )

    # Create authorized_keys
    authorized_keys_path = sshd_dir / "authorized_keys"
    authorized_keys_path.write_text(authorized_keys_content)

    # Create sshd_config
    sshd_config_path = etc_dir / "sshd_config"
    current_user = os.environ.get("USER", "root")
    sshd_config = f"""
Port {port}
ListenAddress 127.0.0.1
HostKey {host_key_path}
AuthorizedKeysFile {authorized_keys_path}
PasswordAuthentication no
ChallengeResponseAuthentication no
UsePAM no
PermitRootLogin yes
PidFile {run_dir}/sshd.pid
StrictModes no
Subsystem sftp /usr/lib/openssh/sftp-server
AllowUsers {current_user}
"""
    sshd_config_path.write_text(sshd_config)

    # Start sshd
    proc = subprocess.Popen(
        [sshd_path, "-D", "-f", str(sshd_config_path), "-e"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        # Wait for sshd to start
        wait_for(
            lambda: is_port_open(port),
            timeout=10.0,
            error_message="sshd failed to start within timeout",
        )

        yield port, host_key_path

    finally:
        # Stop sshd
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
