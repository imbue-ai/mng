import json
import os
import tempfile
from collections.abc import Mapping
from collections.abc import Sequence
from datetime import datetime
from datetime import timezone
from pathlib import Path
from typing import Final

import click
from loguru import logger
from pydantic import Field

from imbue.imbue_common.frozen_model import FrozenModel
from imbue.mng.primitives import AgentReference
from imbue.mng.primitives import HostReference
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


class CachedAgentEntry(FrozenModel):
    """Cached metadata about an agent for provider-aware lookups."""

    name: str = Field(description="Human-readable agent name")
    id: str = Field(description="Unique agent identifier")
    provider: str = Field(description="Provider instance name that owns the agent's host")
    host_name: str = Field(description="Human-readable host name")
    host_id: str = Field(description="Unique host identifier")


def write_agent_names_cache(
    cache_dir: Path,
    agents_by_host: Mapping[HostReference, Sequence[AgentReference]],
) -> None:
    """Write agent data to the completion cache file (best-effort).

    Writes a JSON file with per-agent metadata (including provider) so that
    shell completion and provider-aware lookups can read it without importing
    the mng config system. A backward-compatible "names" key is also written
    so that the lightweight shell completer (complete.py) continues to work.

    Catches OSError from cache writes so filesystem failures do not break
    the caller. Other exceptions are allowed to propagate.
    """
    try:
        entries: list[CachedAgentEntry] = []
        for host_ref, agent_refs in agents_by_host.items():
            for agent_ref in agent_refs:
                entries.append(
                    CachedAgentEntry(
                        name=str(agent_ref.agent_name),
                        id=str(agent_ref.agent_id),
                        provider=str(host_ref.provider_name),
                        host_name=str(host_ref.host_name),
                        host_id=str(host_ref.host_id),
                    )
                )

        # Backward-compatible names list for the lightweight shell completer
        names = sorted({entry.name for entry in entries})

        cache_data = {
            "agents": [entry.model_dump() for entry in entries],
            "names": names,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        cache_path = cache_dir / AGENT_COMPLETIONS_CACHE_FILENAME
        atomic_write(cache_path, json.dumps(cache_data))
    except OSError:
        logger.debug("Failed to write agent name completion cache")


def read_provider_names_for_identifiers(
    cache_dir: Path,
    identifiers: Sequence[str],
) -> tuple[str, ...] | None:
    """Look up which providers own the given agent identifiers, using the cache.

    Returns a tuple of provider names (always including "local") if every
    identifier is found in the cache, or None if the cache is missing/corrupt
    or any identifier cannot be resolved.
    """
    try:
        cache_path = cache_dir / AGENT_COMPLETIONS_CACHE_FILENAME
        if not cache_path.is_file():
            return None
        raw = json.loads(cache_path.read_text())
    except (json.JSONDecodeError, OSError):
        return None

    agents_list = raw.get("agents")
    if not isinstance(agents_list, list):
        return None

    # Build lookup dicts: name -> set of providers, id -> set of providers
    providers_by_name: dict[str, set[str]] = {}
    providers_by_id: dict[str, set[str]] = {}
    for entry in agents_list:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        agent_id = entry.get("id")
        provider = entry.get("provider")
        if not isinstance(provider, str):
            continue
        if isinstance(name, str):
            providers_by_name.setdefault(name, set()).add(provider)
        if isinstance(agent_id, str):
            providers_by_id.setdefault(agent_id, set()).add(provider)

    # Resolve each identifier against both name and id lookups
    matched_providers: set[str] = set()
    for identifier in identifiers:
        name_match = providers_by_name.get(identifier)
        id_match = providers_by_id.get(identifier)
        if name_match is None and id_match is None:
            return None
        if name_match is not None:
            matched_providers.update(name_match)
        if id_match is not None:
            matched_providers.update(id_match)

    # Always include "local" since local filesystem operations are cheap
    matched_providers.add("local")
    return tuple(sorted(matched_providers))
