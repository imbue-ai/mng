import json
from typing import Final

import click
from loguru import logger

from imbue.mng.utils.agent_cache import get_completion_cache_dir
from imbue.mng.utils.click_utils import detect_alias_to_canonical
from imbue.mng.utils.file_utils import atomic_write

COMMAND_COMPLETIONS_CACHE_FILENAME: Final[str] = ".command_completions.json"


# Commands whose positional arguments should complete against agent names.
# This list is used by the cache writer to populate agent_name_arguments
# in the completions cache. The lightweight completer (complete.py) reads
# this field to decide when to offer agent name completions.
_AGENT_NAME_COMMANDS: Final[frozenset[str]] = frozenset(
    {
        "connect",
        "destroy",
        "exec",
        "limit",
        "logs",
        "message",
        "pair",
        "provision",
        "pull",
        "push",
        "rename",
        "start",
        "stop",
    }
)


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

        canonical_names: set[str] = set()
        for name, cmd in cli_group.commands.items():
            # Skip alias entries -- only process canonical command names
            if name in alias_to_canonical:
                continue

            canonical_name = cmd.name or name
            canonical_names.add(canonical_name)

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

        cache_data: dict[str, object] = {
            "commands": all_command_names,
            "aliases": alias_to_canonical,
            "subcommand_by_command": subcommand_by_command,
            "options_by_command": options_by_command,
            "option_choices": option_choices,
            "agent_name_arguments": sorted(_AGENT_NAME_COMMANDS & canonical_names),
        }

        cache_path = get_completion_cache_dir() / COMMAND_COMPLETIONS_CACHE_FILENAME
        atomic_write(cache_path, json.dumps(cache_data))
    except OSError:
        logger.debug("Failed to write CLI completions cache")
