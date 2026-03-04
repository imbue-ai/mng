"""Unit tests for the mng-notifications plugin registration."""

from collections.abc import Sequence

import click

from imbue.mng_notifications.plugin import register_cli_commands


def test_register_cli_commands_returns_watch_command() -> None:
    """Verify that register_cli_commands returns the watch command."""
    result = register_cli_commands()

    assert result is not None
    assert isinstance(result, Sequence)
    assert len(result) == 1
    assert isinstance(result[0], click.Command)
    assert result[0].name == "watch"
