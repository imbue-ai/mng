"""Tests for CLI command aliases."""

import click

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
