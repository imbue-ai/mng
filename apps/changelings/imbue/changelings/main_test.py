# Tests for the changeling CLI entry point.

from click.testing import CliRunner

from imbue.changelings.main import cli


def test_cli_is_a_group() -> None:
    """The cli should be a Click group with subcommands."""
    assert hasattr(cli, "commands")


def test_cli_has_add_command() -> None:
    """The add subcommand should be registered."""
    assert "add" in cli.commands


def test_cli_has_remove_command() -> None:
    """The remove subcommand should be registered."""
    assert "remove" in cli.commands


def test_cli_has_list_command() -> None:
    """The list subcommand should be registered."""
    assert "list" in cli.commands


def test_cli_has_update_command() -> None:
    """The update subcommand should be registered."""
    assert "update" in cli.commands


def test_cli_has_run_command() -> None:
    """The run subcommand should be registered."""
    assert "run" in cli.commands


def test_cli_has_status_command() -> None:
    """The status subcommand should be registered."""
    assert "status" in cli.commands


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
