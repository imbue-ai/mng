"""Integration tests for the schedule CLI command."""

import pluggy
from click.testing import CliRunner

from imbue.mng_schedule.cli import schedule


def test_schedule_add_requires_command_option(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that schedule add requires --command."""
    result = cli_runner.invoke(
        schedule,
        ["add", "--schedule", "0 2 * * *", "--provider", "local"],
        obj=plugin_manager,
    )
    assert result.exit_code != 0
    assert "--command" in result.output


def test_schedule_add_requires_schedule_option(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that schedule add requires --schedule."""
    result = cli_runner.invoke(
        schedule,
        ["add", "--command", "create", "--provider", "local"],
        obj=plugin_manager,
    )
    assert result.exit_code != 0
    assert "--schedule" in result.output


def test_schedule_add_requires_provider_option(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that schedule add requires --provider."""
    result = cli_runner.invoke(
        schedule,
        ["add", "--command", "create", "--schedule", "0 2 * * *"],
        obj=plugin_manager,
    )
    assert result.exit_code != 0
    assert "--provider" in result.output
