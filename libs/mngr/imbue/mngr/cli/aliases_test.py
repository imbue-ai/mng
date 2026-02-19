"""Tests for CLI command aliases and top-level group behavior."""

import click
import pytest
from click.testing import CliRunner

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

    A registered name is an alias if it differs from the command's own name
    (i.e. it was added via cli.add_command(cmd, name="alias")).
    """
    all_declared_aliases = {alias for aliases in COMMAND_ALIASES.values() for alias in aliases}

    undeclared = [name for name, cmd in cli.commands.items() if name != cmd.name and name not in all_declared_aliases]

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


def test_no_args_writes_help_to_stdout_not_stderr(cli_runner: CliRunner) -> None:
    """Invoking mngr with no arguments should print help to stdout and exit 0.

    Click's default behavior for groups is to raise NoArgsIsHelpError which writes
    help to stderr and exits with code 2. Our AliasAwareGroup overrides this to
    write to stdout and exit cleanly, matching the behavior of --help.
    """
    result = cli_runner.invoke(cli, [])
    assert result.exit_code == 0
    assert "Usage:" in result.output
    assert "Commands:" in result.output


def test_no_args_output_matches_help_flag(cli_runner: CliRunner) -> None:
    """Invoking mngr with no args should produce the same output as --help."""
    no_args_result = cli_runner.invoke(cli, [])
    help_result = cli_runner.invoke(cli, ["--help"])
    assert no_args_result.output == help_result.output
    assert no_args_result.exit_code == help_result.exit_code


def test_subgroup_no_args_writes_to_stdout(cli_runner: CliRunner) -> None:
    """Subgroups that use invoke_without_command should write help to stdout when invoked with no subcommand.

    Note: snapshot is excluded because it uses DefaultCommandGroup which defaults
    to running the 'create' subcommand when no args are given.
    """
    for subcommand in ["plugin", "config"]:
        result = cli_runner.invoke(cli, [subcommand])
        assert result.exit_code == 0, f"{subcommand} exited with {result.exit_code}"
        # Some subgroups use git-style help (NAME section) while others use Click's default (Usage:)
        has_help = "Usage:" in result.output or "NAME" in result.output
        assert has_help, f"{subcommand} did not write help to stdout"
