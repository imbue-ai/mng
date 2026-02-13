# Tests for the changeling CLI entry point.

import pytest
from click.testing import CliRunner

from imbue.changelings.main import cli


@pytest.mark.parametrize("command_name", ["add", "remove", "list", "update", "run", "status"])
def test_cli_has_expected_command(command_name: str) -> None:
    """All expected subcommands should be registered on the CLI group."""
    assert command_name in cli.commands


def test_cli_help_includes_description() -> None:
    """The CLI help text should describe what changelings are."""
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])

    assert result.exit_code == 0
    assert "nightly autonomous agents" in result.output


def test_cli_no_args_shows_usage() -> None:
    """Invoking the CLI with no args should show usage information."""
    runner = CliRunner()
    result = runner.invoke(cli, [])

    assert "Usage" in result.output
