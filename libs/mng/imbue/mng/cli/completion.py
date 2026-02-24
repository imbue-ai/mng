import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Final

import click
from click.shell_completion import CompletionItem

from imbue.mng.config.pre_readers import read_default_host_dir

AGENT_COMPLETIONS_CACHE_FILENAME: Final[str] = ".agent_completions.json"
COMMAND_COMPLETIONS_CACHE_FILENAME: Final[str] = ".command_completions.json"
_BACKGROUND_REFRESH_COOLDOWN_SECONDS: Final[int] = 30


def get_host_dir() -> Path:
    """Resolve the host directory using the full config precedence.

    Delegates to the lightweight pre-reader which checks (highest to lowest):
    1. MNG_HOST_DIR environment variable
    2. default_host_dir from config files
    3. ~/.{MNG_ROOT_NAME} fallback (defaults to ~/.mng)
    """
    return read_default_host_dir()


# =============================================================================
# Agent name completion (read from runtime cache)
# =============================================================================


def _read_agent_names_from_cache() -> list[str]:
    """Read agent names from the completion cache file.

    Reads {host_dir}/.agent_completions.json and returns the "names" list.
    The cache is written by write_agent_names_cache() in completion_writer.py.

    Returns an empty list on expected errors (missing file, malformed JSON).
    Callers are responsible for guarding against unexpected exceptions.
    """
    try:
        cache_path = get_host_dir() / AGENT_COMPLETIONS_CACHE_FILENAME
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
    """Fire-and-forget a background `mng list` to refresh the completion cache.

    Spawns a detached subprocess so shell completion returns immediately.
    Skips the refresh if the cache was updated within the last N seconds
    to avoid excessive subprocess spawning.

    Catches OSError from subprocess spawning. Callers are responsible for
    guarding against unexpected exceptions.
    """
    try:
        cache_path = get_host_dir() / AGENT_COMPLETIONS_CACHE_FILENAME
        if cache_path.is_file():
            age = time.time() - cache_path.stat().st_mtime
            if age < _BACKGROUND_REFRESH_COOLDOWN_SECONDS:
                return

        # Uses subprocess.Popen directly instead of ConcurrencyGroup's
        # run_background because the child must outlive the parent process
        # (start_new_session=True). run_background doesn't support detaching.
        devnull = subprocess.DEVNULL
        subprocess.Popen(
            [sys.executable, "-c", "from imbue.mng.main import cli; cli(['list', '--format', 'json', '-q'])"],
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
    """Click shell_complete callback that provides agent name completions.

    Never raises -- shell completion must not interfere with normal CLI operation.
    """
    try:
        names = _read_agent_names_from_cache()
        _trigger_background_cache_refresh()
        return [CompletionItem(name) for name in names if name.startswith(incomplete)]
    except Exception:
        return []


# =============================================================================
# CLI command/subcommand completion (read from runtime cache)
# =============================================================================
#
# These functions read a JSON file listing all CLI commands and subcommands.
# The file is written to {host_dir}/.command_completions.json by
# write_cli_completions_cache() in completion_writer.py, called from the
# list command (which is triggered by the background tab completion refresh).
#
# This is analogous to the agent name cache above: tab completion reads from
# a cached list rather than discovering commands live.


def _get_cli_completions_path() -> Path:
    """Return the path to the CLI completions cache file in the host dir."""
    return get_host_dir() / COMMAND_COMPLETIONS_CACHE_FILENAME


def _read_cli_completions_file() -> dict | None:
    """Read the CLI completions cache file.

    Returns the parsed JSON data, or None on expected errors (missing file,
    malformed JSON). Callers are responsible for guarding against unexpected
    exceptions.
    """
    try:
        path = _get_cli_completions_path()
        if not path.is_file():
            return None
        data = json.loads(path.read_text())
        if not isinstance(data, dict):
            return None
        return data
    except (json.JSONDecodeError, OSError):
        return None


def read_cached_commands() -> list[str] | None:
    """Read cached top-level command names from the completions cache.

    Returns a sorted list of command names (including aliases), or None if the
    cache does not exist or is malformed.
    """
    data = _read_cli_completions_file()
    if data is None:
        return None
    commands = data.get("commands")
    if not isinstance(commands, list):
        return None
    result = [name for name in commands if isinstance(name, str) and name]
    return sorted(result) if result else None


def read_cached_subcommands(command_name: str) -> list[str] | None:
    """Read cached subcommand names for a given parent command.

    Returns a sorted list of subcommand names, or None if the cache does not
    exist, is malformed, or the command has no cached subcommands.
    """
    data = _read_cli_completions_file()
    if data is None:
        return None
    subcommand_by_command = data.get("subcommand_by_command")
    if not isinstance(subcommand_by_command, dict):
        return None
    subcommands = subcommand_by_command.get(command_name)
    if not isinstance(subcommands, list):
        return None
    result = [name for name in subcommands if isinstance(name, str) and name]
    return sorted(result) if result else None


class CachedCompletionGroup(click.Group):
    """Base class for click.Group subclasses that reads subcommand completions from the cache.

    Subclasses must set `_completion_cache_key` to the command name used as
    the lookup key in the CLI completions cache.
    """

    _completion_cache_key: str

    def shell_complete(self, ctx: click.Context, incomplete: str) -> list[CompletionItem]:
        try:
            cached = read_cached_subcommands(self._completion_cache_key)
            if cached is not None:
                completions = [CompletionItem(name) for name in cached if name.startswith(incomplete)]
                completions.extend(click.Command.shell_complete(self, ctx, incomplete))
                return completions
        except Exception:
            pass
        return super().shell_complete(ctx, incomplete)
