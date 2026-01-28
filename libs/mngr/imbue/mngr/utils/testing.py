import json
import os
import re
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
from loguru import logger

from imbue.mngr.config.data_types import MngrConfig
from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.primitives import ProviderInstanceName
from imbue.mngr.providers.local.instance import LocalProviderInstance

# Prefix used for test environments
MODAL_TEST_ENV_PREFIX: Final[str] = "mngr_test-"

# Pattern to match test environment names: mngr_test-YYYY-MM-DD-HH-MM-SS
# The name may have additional suffixes (like user_id)
MODAL_TEST_ENV_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^mngr_test-(\d{4})-(\d{2})-(\d{2})-(\d{2})-(\d{2})-(\d{2})"
)


# FIXME: this is stupid--replace with a context manager instead. Do we already have one? Is there a built-in pytest fixture for this?
def restore_env_var(name: str, original_value: str | None) -> None:
    """Restore an environment variable to its original value.

    Use this in test cleanup to restore environment variables that were modified
    during test execution. Pass the original value (or None if it was not set).
    """
    if original_value is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = original_value


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


def cleanup_tmux_session(session_name: str) -> None:
    """Clean up a tmux session if it exists."""
    subprocess.run(
        ["tmux", "kill-session", "-t", session_name],
        capture_output=True,
    )


@contextmanager
def tmux_session_cleanup(session_name: str) -> Generator[str, None, None]:
    """Context manager that cleans up a tmux session on exit."""
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
) -> LocalProviderInstance:
    """Create a LocalProviderInstance with the given host_dir and config."""
    pm = pluggy.PluginManager("mngr")
    mngr_ctx = MngrContext(config=config, pm=pm)
    return LocalProviderInstance(
        name=ProviderInstanceName(name),
        host_dir=host_dir,
        mngr_ctx=mngr_ctx,
    )


def make_mngr_ctx(default_host_dir: Path, prefix: str) -> MngrContext:
    """Create a MngrContext with the given default_host_dir, prefix, and a basic plugin manager."""
    config = MngrConfig(default_host_dir=default_host_dir, prefix=prefix)
    pm = pluggy.PluginManager("mngr")
    return MngrContext(config=config, pm=pm)


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
                    logger.warning("Failed to delete Modal volume {} in environment {}: {}", volume_name, environment_name, e)
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
