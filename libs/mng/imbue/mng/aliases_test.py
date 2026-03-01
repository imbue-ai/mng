"""Tests for properties of the assembled CLI group (aliases, naming conventions)."""

import click
import pytest

from imbue.mng.main import cli
from imbue.mng.utils.click_utils import detect_alias_to_canonical

# Build (alias, canonical) pairs from the CLI group for parametrized test
_ALL_ALIAS_PAIRS: list[tuple[str, str]] = sorted(detect_alias_to_canonical(cli).items())


@pytest.mark.parametrize(("alias", "canonical"), _ALL_ALIAS_PAIRS, ids=[a for a, _ in _ALL_ALIAS_PAIRS])
def test_alias_registered_and_points_to_canonical(alias: str, canonical: str) -> None:
    """Every detected alias must be registered and point to the canonical command."""
    assert alias in cli.commands, f"Alias '{alias}' not registered via cli.add_command"
    assert cli.commands[alias] is cli.commands[canonical], f"Alias '{alias}' does not point to '{canonical}'"


def test_all_cli_commands_are_single_word() -> None:
    """Ensure all CLI command names are single words (no spaces, hyphens, or underscores).

    This is CRITICAL for the MNG_COMMANDS_<COMMANDNAME>_<PARAMNAME> env var parsing
    to work correctly. If command names contained underscores, parsing would be ambiguous.

    For example, if a command was named "foo_bar" and a param was "baz", the env var
    would be "MNG_COMMANDS_FOO_BAR_BAZ", which could be interpreted as either:
        - command="foo", param="bar_baz"
        - command="foo_bar", param="baz"

    By requiring single-word commands, we avoid this ambiguity.

    Any future plugins that register custom commands MUST also follow this convention.
    """
    assert isinstance(cli, click.Group), "cli should be a click.Group"

    invalid_commands = []
    for command_name in cli.commands.keys():
        if " " in command_name or "-" in command_name or "_" in command_name:
            invalid_commands.append(command_name)

    assert not invalid_commands, (
        f"CLI command names must be single words (no spaces, hyphens, or underscores) "
        f"for MNG_COMMANDS_<COMMANDNAME>_<PARAMNAME> env var parsing to work. "
        f"Invalid commands: {invalid_commands}"
    )
