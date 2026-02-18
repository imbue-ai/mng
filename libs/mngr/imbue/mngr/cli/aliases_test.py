"""Tests for CLI command aliases."""

import click
import pytest

from imbue.mngr.main import COMMAND_ALIASES
from imbue.mngr.main import cli


def _complete_names(incomplete: str) -> list[str]:
    """Return the completion values for a given incomplete command prefix."""
    ctx = click.Context(cli)
    completions = cli.shell_complete(ctx, incomplete)
    return [item.value for item in completions]


# Build (alias, canonical) pairs for parametrized test
_ALL_ALIAS_PAIRS: list[tuple[str, str]] = [
    (alias, canonical) for canonical, aliases in COMMAND_ALIASES.items() for alias in aliases
]


@pytest.mark.parametrize(("alias", "canonical"), _ALL_ALIAS_PAIRS, ids=[a for a, _ in _ALL_ALIAS_PAIRS])
def test_alias_registered_and_points_to_canonical(alias: str, canonical: str) -> None:
    """Every alias in COMMAND_ALIASES must be registered and point to the canonical command."""
    assert alias in cli.commands, f"Alias '{alias}' not registered via cli.add_command"
    assert cli.commands[alias] is cli.commands[canonical], f"Alias '{alias}' does not point to '{canonical}'"


def test_no_undeclared_aliases() -> None:
    """Every registered alias must be declared in COMMAND_ALIASES.

    A command in cli.commands is an alias if it shares its click.Command
    object with another registered name (i.e. two names point to the same
    command). Every such alias must appear in COMMAND_ALIASES.
    """
    all_declared_aliases = {alias for aliases in COMMAND_ALIASES.values() for alias in aliases}

    # Build a map from command object id to canonical name(s)
    canonical_names = {name for name in COMMAND_ALIASES} | {
        cmd.name for cmd in cli.commands.values() if cmd.name is not None and cmd.name not in all_declared_aliases
    }

    undeclared: list[str] = []
    for name in cli.commands:
        if name in canonical_names:
            continue
        if name not in all_declared_aliases:
            undeclared.append(name)

    assert not undeclared, f"Commands registered as aliases but not declared in COMMAND_ALIASES: {undeclared}"


def test_shell_complete_drops_alias_when_canonical_present() -> None:
    """Completing 'con' should return 'connect' and 'config', not 'conn'."""
    names = _complete_names("con")
    assert "connect" in names
    assert "config" in names
    assert "conn" not in names


def test_shell_complete_drops_all_aliases_for_broad_prefix() -> None:
    """Completing 'c' should return canonical names only, no aliases."""
    names = _complete_names("c")
    assert "config" in names
    assert "connect" in names
    assert "create" in names
    assert "clone" in names
    # aliases should be dropped
    assert "c" not in names
    assert "cfg" not in names
    assert "conn" not in names


def test_shell_complete_returns_all_commands_for_empty_prefix() -> None:
    """Completing '' should return all canonical commands, no aliases."""
    names = _complete_names("")
    # spot-check some canonical names
    assert "list" in names
    assert "destroy" in names
    assert "message" in names
    # aliases should be dropped
    assert "ls" not in names
    assert "rm" not in names
    assert "msg" not in names
