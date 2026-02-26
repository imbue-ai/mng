import json
import os
import tempfile
from datetime import datetime
from datetime import timezone
from pathlib import Path
from typing import Final

import click
from loguru import logger

from imbue.mng.utils.click_utils import detect_alias_to_canonical
from imbue.mng.utils.file_utils import atomic_write

AGENT_COMPLETIONS_CACHE_FILENAME: Final[str] = ".agent_completions.json"
COMMAND_COMPLETIONS_CACHE_FILENAME: Final[str] = ".command_completions.json"


def get_completion_cache_dir() -> Path:
    """Return the directory used for completion cache files.

    Uses MNG_COMPLETION_CACHE_DIR if set, otherwise a fixed path under the
    system temp directory namespaced by uid to avoid collisions between users.
    The directory is created if it does not exist.
    """
    env_dir = os.environ.get("MNG_COMPLETION_CACHE_DIR")
    if env_dir:
        cache_dir = Path(env_dir)
    else:
        cache_dir = Path(tempfile.gettempdir()) / f"mng-completions-{os.getuid()}"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def complete_agent_name(
    ctx: click.Context,
    param: click.Parameter,
    incomplete: str,
) -> list:
    """Marker callback for click arguments that accept agent names.

    The cache writer detects this callback (via identity check) to populate
    the agent_name_arguments field in the completions cache. The lightweight
    completer (complete.py) handles the actual completion at runtime.
    """
    return []


# =============================================================================
# Cache writers
# =============================================================================


def _extract_options_for_command(cmd: click.Command) -> list[str]:
    """Extract all --long option names from a click command."""
    options: list[str] = []
    for param in cmd.params:
        if isinstance(param, click.Option):
            for opt in param.opts + param.secondary_opts:
                if opt.startswith("--"):
                    options.append(opt)
    return sorted(options)


def _extract_choices_for_command(cmd: click.Command, key_prefix: str) -> dict[str, list[str]]:
    """Extract option choices (click.Choice values) from a click command.

    Returns a dict mapping "key_prefix.--option" to the list of valid choices.
    """
    choices: dict[str, list[str]] = {}
    for param in cmd.params:
        if isinstance(param, click.Option) and isinstance(param.type, click.Choice):
            choice_values: list[str] = [str(c) for c in param.type.choices]
            for opt in param.opts + param.secondary_opts:
                if opt.startswith("--"):
                    choices[f"{key_prefix}.{opt}"] = choice_values
    return choices


def _has_agent_name_argument(cmd: click.Command) -> bool:
    """Check if a command has an argument using complete_agent_name for shell completion."""
    for param in cmd.params:
        if isinstance(param, click.Argument):
            # click stores the shell_complete callback in _custom_shell_complete
            custom_complete = vars(param).get("_custom_shell_complete")
            if custom_complete is complete_agent_name:
                return True
    return False


def write_cli_completions_cache(cli_group: click.Group) -> None:
    """Write all CLI commands, options, and choices to the completions cache (best-effort).

    Walks the CLI command tree and writes the result to
    .command_completions.json in the completion cache directory. This is called
    from the list command (triggered by background tab completion refresh) to
    keep the cache up to date with installed plugins.

    Aliases are auto-detected: any command registered under a name different
    from its canonical cmd.name is treated as an alias.

    Catches OSError from cache writes so filesystem failures do not break
    CLI commands. Other exceptions are allowed to propagate.
    """
    try:
        all_command_names = sorted(cli_group.commands.keys())
        alias_to_canonical = detect_alias_to_canonical(cli_group)

        subcommand_by_command: dict[str, list[str]] = {}
        options_by_command: dict[str, list[str]] = {}
        option_choices: dict[str, list[str]] = {}
        agent_name_arguments: list[str] = []

        for name, cmd in cli_group.commands.items():
            # Skip alias entries -- only process canonical command names
            if name in alias_to_canonical:
                continue

            canonical_name = cmd.name or name

            if isinstance(cmd, click.Group) and cmd.commands:
                if canonical_name not in subcommand_by_command:
                    subcommand_by_command[canonical_name] = sorted(cmd.commands.keys())

                # Extract options and choices for subcommands
                for sub_name, sub_cmd in cmd.commands.items():
                    sub_key = f"{canonical_name}.{sub_name}"
                    sub_options = _extract_options_for_command(sub_cmd)
                    if sub_options:
                        options_by_command[sub_key] = sub_options
                    option_choices.update(_extract_choices_for_command(sub_cmd, sub_key))

                # Also extract options for the group command itself
                group_options = _extract_options_for_command(cmd)
                if group_options:
                    options_by_command[canonical_name] = group_options
                option_choices.update(_extract_choices_for_command(cmd, canonical_name))
            else:
                # Simple command (not a group)
                cmd_options = _extract_options_for_command(cmd)
                if cmd_options:
                    options_by_command[canonical_name] = cmd_options
                option_choices.update(_extract_choices_for_command(cmd, canonical_name))

                if _has_agent_name_argument(cmd):
                    agent_name_arguments.append(canonical_name)

        cache_data: dict[str, object] = {
            "commands": all_command_names,
            "aliases": alias_to_canonical,
            "subcommand_by_command": subcommand_by_command,
            "options_by_command": options_by_command,
            "option_choices": option_choices,
            "agent_name_arguments": sorted(agent_name_arguments),
        }

        cache_path = get_completion_cache_dir() / COMMAND_COMPLETIONS_CACHE_FILENAME
        atomic_write(cache_path, json.dumps(cache_data))
    except OSError:
        logger.debug("Failed to write CLI completions cache")


def write_agent_names_cache(host_dir: Path, agent_names: list[str]) -> None:
    """Write agent names to the completion cache file (best-effort).

    Writes a JSON file with agent names so that shell completion can read it
    without importing the mng config system. The cache file is written to
    {host_dir}/.agent_completions.json.

    Catches OSError from cache writes so filesystem failures do not break
    the caller. Other exceptions are allowed to propagate.
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
