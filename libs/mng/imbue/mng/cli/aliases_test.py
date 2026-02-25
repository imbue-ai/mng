"""Tests for CLI command aliases."""

import click
import pytest

from imbue.mng.main import cli
from imbue.mng.utils.click_utils import detect_alias_to_canonical


def _complete_names(incomplete: str) -> list[str]:
    """Return the completion values for a given incomplete command prefix."""
    ctx = click.Context(cli)
    completions = cli.shell_complete(ctx, incomplete)
    return [item.value for item in completions]


# Build (alias, canonical) pairs from the CLI group for parametrized test
_ALL_ALIAS_PAIRS: list[tuple[str, str]] = sorted(detect_alias_to_canonical(cli).items())


@pytest.mark.parametrize(("alias", "canonical"), _ALL_ALIAS_PAIRS, ids=[a for a, _ in _ALL_ALIAS_PAIRS])
def test_alias_registered_and_points_to_canonical(alias: str, canonical: str) -> None:
    """Every detected alias must be registered and point to the canonical command."""
    assert alias in cli.commands, f"Alias '{alias}' not registered via cli.add_command"
    assert cli.commands[alias] is cli.commands[canonical], f"Alias '{alias}' does not point to '{canonical}'"


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
