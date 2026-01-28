"""Tests for CLI command aliases."""

from imbue.mngr.main import cli


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
