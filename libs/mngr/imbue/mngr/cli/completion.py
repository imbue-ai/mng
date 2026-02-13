import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import click
from click.shell_completion import CompletionItem

COMPLETION_CACHE_FILENAME = ".completion_cache.json"
_BACKGROUND_REFRESH_COOLDOWN_SECONDS = 30


def _get_host_dir() -> Path:
    """Resolve the host directory from MNGR_HOST_DIR or the default ~/.mngr."""
    env_host_dir = os.environ.get("MNGR_HOST_DIR")
    return Path(env_host_dir) if env_host_dir else Path.home() / ".mngr"


def _read_agent_names_from_cache() -> list[str]:
    """Read agent names from the completion cache file.

    Reads {host_dir}/.completion_cache.json and returns the "names" list.
    The cache is written by list_agents() in the API layer.

    Returns an empty list if the cache does not exist, is malformed, or any error occurs.
    This function is designed to never raise -- shell completion must not crash.
    """
    try:
        cache_path = _get_host_dir() / COMPLETION_CACHE_FILENAME
        if not cache_path.is_file():
            return []

        data = json.loads(cache_path.read_text())
        names = data.get("names")
        if not isinstance(names, list):
            return []

        return sorted(name for name in names if isinstance(name, str) and name)
    except (json.JSONDecodeError, OSError):
        return []


def _trigger_background_cache_refresh() -> None:
    """Fire-and-forget a background `mngr list` to refresh the completion cache.

    Spawns a detached subprocess so shell completion returns immediately.
    Skips the refresh if the cache was updated within the last N seconds
    to avoid excessive subprocess spawning.

    This function never raises -- background refresh failures are silently ignored.
    """
    try:
        cache_path = _get_host_dir() / COMPLETION_CACHE_FILENAME
        if cache_path.is_file():
            age = time.time() - cache_path.stat().st_mtime
            if age < _BACKGROUND_REFRESH_COOLDOWN_SECONDS:
                return

        mngr_path = shutil.which("mngr")
        if mngr_path is None:
            return

        devnull = subprocess.DEVNULL
        subprocess.Popen(
            [mngr_path, "list", "--format", "json", "-q"],
            stdout=devnull,
            stderr=devnull,
            start_new_session=True,
        )
    except OSError:
        pass


def complete_agent_name(
    ctx: click.Context,
    param: click.Parameter,
    incomplete: str,
) -> list[CompletionItem]:
    """Click shell_complete callback that provides agent name completions."""
    names = _read_agent_names_from_cache()
    _trigger_background_cache_refresh()
    return [CompletionItem(name) for name in names if name.startswith(incomplete)]
