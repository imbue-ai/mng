import json
import os
from datetime import datetime
from datetime import timezone
from pathlib import Path

import click
from loguru import logger

from imbue.mng.cli.completion import CLI_COMPLETIONS_FILENAME
from imbue.mng.cli.completion import COMPLETION_CACHE_FILENAME
from imbue.mng.utils.file_utils import atomic_write


def _get_host_dir() -> Path:
    """Resolve the host directory from MNG_HOST_DIR or the default ~/.mng."""
    env_host_dir = os.environ.get("MNG_HOST_DIR")
    return Path(env_host_dir) if env_host_dir else Path.home() / ".mng"


def write_cli_completions_cache(cli_group: click.Group) -> None:
    """Write all CLI commands and subcommands to the completions cache (best-effort).

    Walks the CLI command tree and writes the result to
    {host_dir}/.cli_completions.json. This is called on every CLI invocation
    so the cache stays up to date with installed plugins.

    This function never raises -- cache write failures must not break CLI commands.
    """
    try:
        all_command_names = sorted(cli_group.commands.keys())

        subcommand_by_command: dict[str, list[str]] = {}
        for name, cmd in cli_group.commands.items():
            if isinstance(cmd, click.Group) and cmd.commands:
                canonical_name = cmd.name or name
                if canonical_name not in subcommand_by_command:
                    subcommand_by_command[canonical_name] = sorted(cmd.commands.keys())

        cache_data = {
            "commands": all_command_names,
            "subcommand_by_command": subcommand_by_command,
        }

        cache_path = _get_host_dir() / CLI_COMPLETIONS_FILENAME
        atomic_write(cache_path, json.dumps(cache_data))
    except OSError:
        logger.debug("Failed to write CLI completions cache")


def write_agent_names_cache(host_dir: Path, agent_names: list[str]) -> None:
    """Write agent names to the completion cache file (best-effort).

    Writes a JSON file with agent names so that shell completion can read it
    without importing the mng config system. The cache file is written to
    {host_dir}/.completion_cache.json.

    This function never raises -- cache write failures must not break the caller.
    """
    try:
        cache_data = {
            "names": sorted(set(agent_names)),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        cache_path = host_dir / COMPLETION_CACHE_FILENAME
        atomic_write(cache_path, json.dumps(cache_data))
    except OSError:
        logger.debug("Failed to write agent name completion cache")
