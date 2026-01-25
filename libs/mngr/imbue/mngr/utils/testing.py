import os
import subprocess
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

import pluggy

from imbue.mngr.config.data_types import MngrConfig
from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.primitives import ProviderInstanceName
from imbue.mngr.providers.local.instance import LocalProviderInstance


def get_subprocess_test_env(root_name: str = "mngr-test") -> dict[str, str]:
    """Get environment variables for subprocess calls that prevent loading project config.

    Sets MNGR_ROOT_NAME to a value that doesn't have a corresponding config directory,
    preventing subprocess tests from picking up .mngr/settings.toml which might have
    settings like add_command that would interfere with tests.

    The root_name parameter defaults to "mngr-test" but can be set to a descriptive
    name for your test category (e.g., "mngr-acceptance-test", "mngr-release-test").

    Returns a copy of os.environ with MNGR_ROOT_NAME set to the specified value.
    """
    env = os.environ.copy()
    env["MNGR_ROOT_NAME"] = root_name
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
