"""Tests for CLI command aliases and top-level group behavior."""

import click
from click.testing import CliRunner

from imbue.mngr.main import cli


def _complete_names(incomplete: str) -> list[str]:
    """Return the completion values for a given incomplete command prefix."""
    ctx = click.Context(cli)
    completions = cli.shell_complete(ctx, incomplete)
    return [item.value for item in completions]


def test_ls_alias_exists() -> None:
    """The 'ls' command should be an alias for 'list'."""
    assert "ls" in cli.commands
    assert cli.commands["ls"] is cli.commands["list"]


def test_conn_alias_exists() -> None:
    """The 'conn' command should be an alias for 'connect'."""
    assert "conn" in cli.commands
    assert cli.commands["conn"] is cli.commands["connect"]


def test_c_alias_exists() -> None:
    """The 'c' command should be an alias for 'create'."""
    assert "c" in cli.commands
    assert cli.commands["c"] is cli.commands["create"]


def test_cfg_alias_exists() -> None:
    """The 'cfg' command should be an alias for 'config'."""
    assert "cfg" in cli.commands
    assert cli.commands["cfg"] is cli.commands["config"]


def test_msg_alias_exists() -> None:
    """The 'msg' command should be an alias for 'message'."""
    assert "msg" in cli.commands
    assert cli.commands["msg"] is cli.commands["message"]


def test_rm_alias_exists() -> None:
    """The 'rm' command should be an alias for 'destroy'."""
    assert "rm" in cli.commands
    assert cli.commands["rm"] is cli.commands["destroy"]


def test_lim_alias_exists() -> None:
    """The 'lim' command should be an alias for 'limit'."""
    assert "lim" in cli.commands
    assert cli.commands["lim"] is cli.commands["limit"]


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
    """Subgroups (snapshot, plugin, config) should write help to stdout when invoked with no subcommand."""
    for subcommand in ["snapshot", "plugin", "config"]:
        result = cli_runner.invoke(cli, [subcommand])
        assert result.exit_code == 0, f"{subcommand} exited with {result.exit_code}"
        # Some subgroups use git-style help (NAME section) while others use Click's default (Usage:)
        has_help = "Usage:" in result.output or "NAME" in result.output
        assert has_help, f"{subcommand} did not write help to stdout"
