import json
from datetime import datetime
from datetime import timezone
from pathlib import Path

import click
from loguru import logger

from imbue.mng.cli.completion import AGENT_COMPLETIONS_CACHE_FILENAME
from imbue.mng.cli.completion import COMMAND_COMPLETIONS_CACHE_FILENAME
from imbue.mng.cli.completion import get_host_dir
from imbue.mng.utils.file_utils import atomic_write


def write_cli_completions_cache(cli_group: click.Group) -> None:
    """Write all CLI commands and subcommands to the completions cache (best-effort).

    Walks the CLI command tree and writes the result to
    {host_dir}/.command_completions.json. This is called from the list command
    (triggered by background tab completion refresh) to keep the cache up to
    date with installed plugins.

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

        cache_path = get_host_dir() / COMMAND_COMPLETIONS_CACHE_FILENAME
        atomic_write(cache_path, json.dumps(cache_data))
    except OSError:
        logger.debug("Failed to write CLI completions cache")


def write_agent_names_cache(host_dir: Path, agent_names: list[str]) -> None:
    """Write agent names to the completion cache file (best-effort).

    Writes a JSON file with agent names so that shell completion can read it
    without importing the mng config system. The cache file is written to
    {host_dir}/.agent_completions.json.

    This function never raises -- cache write failures must not break the caller.
    """
    try:
        cache_data = {
            "names": sorted(set(agent_names)),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        cache_path = host_dir / AGENT_COMPLETIONS_CACHE_FILENAME
        atomic_write(cache_path, json.dumps(cache_data))
    except OSError:
        logger.debug("Failed to write agent name completion cache")
