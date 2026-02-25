"""Lightweight tab completion entrypoint -- stdlib only, no third-party imports.

Reads COMP_WORDS and COMP_CWORD from the environment (same protocol click
uses), resolves the completion context from a JSON cache file, and prints
results. This avoids importing click, pydantic, pluggy, or any plugin code
on every TAB press.

Invoked as: python -m imbue.mng.cli.complete {zsh|bash}
"""

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

_COMMAND_COMPLETIONS_CACHE_FILENAME = ".command_completions.json"
_AGENT_COMPLETIONS_CACHE_FILENAME = ".agent_completions.json"
_BACKGROUND_REFRESH_COOLDOWN_SECONDS = 30


def _get_completion_cache_dir() -> Path:
    """Return the directory used for completion cache files.

    Mirrors get_completion_cache_dir() in completion.py but uses only stdlib.
    """
    env_dir = os.environ.get("MNG_COMPLETION_CACHE_DIR")
    if env_dir:
        return Path(env_dir)
    return Path(tempfile.gettempdir()) / f"mng-completions-{os.getuid()}"


def _read_cache() -> dict:
    """Read the command completions cache file. Returns empty dict on any error."""
    try:
        path = _get_completion_cache_dir() / _COMMAND_COMPLETIONS_CACHE_FILENAME
        if not path.is_file():
            return {}
        data = json.loads(path.read_text())
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return {}


def _read_agent_names() -> list[str]:
    """Read agent names from the agent completions cache file."""
    try:
        path = _get_completion_cache_dir() / _AGENT_COMPLETIONS_CACHE_FILENAME
        if not path.is_file():
            return []
        data = json.loads(path.read_text())
        names = data.get("names")
        if not isinstance(names, list):
            return []
        return sorted(name for name in names if isinstance(name, str) and name)
    except (json.JSONDecodeError, OSError):
        return []


def _trigger_background_refresh() -> None:
    """Fire-and-forget a background process to refresh the completion cache.

    Checks the agent cache age and spawns a detached subprocess if stale.
    """
    try:
        cache_path = _get_completion_cache_dir() / _AGENT_COMPLETIONS_CACHE_FILENAME
        if cache_path.is_file():
            age = time.time() - cache_path.stat().st_mtime
            if age < _BACKGROUND_REFRESH_COOLDOWN_SECONDS:
                return

        devnull = subprocess.DEVNULL
        subprocess.Popen(
            [sys.executable, "-c", "from imbue.mng.main import cli; cli(['list', '--format', 'json', '-q'])"],
            stdout=devnull,
            stderr=devnull,
            start_new_session=True,
        )
    except OSError:
        pass


def _get_completions(shell: str) -> list[str]:
    """Compute completion candidates from environment variables and the cache."""
    comp_words_raw = os.environ.get("COMP_WORDS", "")
    comp_cword_raw = os.environ.get("COMP_CWORD", "")

    try:
        comp_cword = int(comp_cword_raw)
    except ValueError:
        return []

    words = comp_words_raw.split()

    # Determine the incomplete word being completed
    if comp_cword < len(words):
        incomplete = words[comp_cword]
    else:
        incomplete = ""

    cache = _read_cache()
    commands: list[str] = cache.get("commands", [])
    aliases: dict[str, str] = cache.get("aliases", {})
    subcommand_by_command: dict[str, list[str]] = cache.get("subcommand_by_command", {})
    options_by_command: dict[str, list[str]] = cache.get("options_by_command", {})
    option_choices: dict[str, list[str]] = cache.get("option_choices", {})
    agent_name_arguments: list[str] = cache.get("agent_name_arguments", [])

    # Resolve the command and subcommand from the words already typed
    resolved_command: str | None = None
    resolved_subcommand: str | None = None

    # words[0] = "mng", words[1] = command, words[2] = subcommand (if group)
    if len(words) > 1 and comp_cword > 1:
        # Word at index 1 is fully typed (not being completed)
        raw_cmd = words[1]
        resolved_command = aliases.get(raw_cmd, raw_cmd)
    elif len(words) > 1 and comp_cword == 1:
        # We are completing the command name itself
        pass

    is_group = resolved_command is not None and resolved_command in subcommand_by_command

    if resolved_command is not None and is_group and len(words) > 2 and comp_cword > 2:
        resolved_subcommand = words[2]

    # Determine the previous word (for option value completion)
    prev_word: str | None = None
    if comp_cword >= 1 and comp_cword - 1 < len(words):
        prev_word = words[comp_cword - 1]

    # Determine the command key for option lookups
    if resolved_subcommand is not None:
        option_key = f"{resolved_command}.{resolved_subcommand}"
    elif resolved_command is not None:
        option_key = resolved_command
    else:
        option_key = ""

    candidates: list[str]

    if comp_cword == 1:
        # Completing the command name (position 1)
        candidates = _filter_aliases(commands, aliases, incomplete)
    elif is_group and comp_cword == 2:
        # Completing a subcommand of a group
        assert resolved_command is not None
        candidates = subcommand_by_command.get(resolved_command, [])
    elif prev_word is not None and prev_word.startswith("--"):
        # Check if previous word is an option with choices
        choice_key = f"{option_key}.{prev_word}"
        if choice_key in option_choices:
            candidates = option_choices[choice_key]
        elif incomplete.startswith("--"):
            candidates = options_by_command.get(option_key, [])
        else:
            # Previous word is a flag, current word doesn't start with --
            # Could be a value for an option without predefined choices
            candidates = _get_positional_candidates(resolved_command, agent_name_arguments)
    elif incomplete.startswith("--"):
        candidates = options_by_command.get(option_key, [])
    else:
        candidates = _get_positional_candidates(resolved_command, agent_name_arguments)

    return [c for c in candidates if c.startswith(incomplete)]


def _filter_aliases(
    commands: list[str],
    aliases: dict[str, str],
    incomplete: str,
) -> list[str]:
    """Filter command candidates, dropping aliases when their canonical name also matches.

    Mirrors the alias filtering logic from AliasAwareGroup.shell_complete.
    """
    matching = [c for c in commands if c.startswith(incomplete)]
    matching_set = set(matching)
    return [c for c in matching if c not in aliases or aliases[c] not in matching_set]


def _get_positional_candidates(
    resolved_command: str | None,
    agent_name_arguments: list[str],
) -> list[str]:
    """Return positional argument candidates (agent names) if applicable."""
    if resolved_command is not None and resolved_command in agent_name_arguments:
        return _read_agent_names()
    return []


def _format_output(completions: list[str], shell: str) -> str:
    """Format completion candidates for the given shell."""
    if shell == "zsh":
        # zsh format: "plain\n{value}\n_" per item (3 lines each)
        lines: list[str] = []
        for value in completions:
            lines.append("plain")
            lines.append(value)
            lines.append("_")
        return "\n".join(lines)
    else:
        # bash format: "plain,{value}" per item (1 line each)
        return "\n".join(f"plain,{value}" for value in completions)


def main() -> None:
    """Entry point for lightweight tab completion."""
    if len(sys.argv) < 2:
        shell = "zsh"
    else:
        shell = sys.argv[1]

    completions = _get_completions(shell)
    output = _format_output(completions, shell)
    if output:
        sys.stdout.write(output + "\n")

    _trigger_background_refresh()


if __name__ == "__main__":
    main()
