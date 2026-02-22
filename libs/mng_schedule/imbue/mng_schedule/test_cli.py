"""Integration tests for the schedule CLI command."""

import pluggy
import pytest
from click.testing import CliRunner

from imbue.mng_schedule.cli import schedule


@pytest.mark.parametrize(
    ("missing_option", "provided_args"),
    [
        ("--command", ["add", "--schedule", "0 2 * * *", "--provider", "local"]),
        ("--schedule", ["add", "--command", "create", "--provider", "local"]),
        ("--provider", ["add", "--command", "create", "--schedule", "0 2 * * *"]),
    ],
)
def test_schedule_add_requires_option(
    missing_option: str,
    provided_args: list[str],
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that schedule add fails when a required option is missing."""
    result = cli_runner.invoke(schedule, provided_args, obj=plugin_manager)
    assert result.exit_code != 0
    assert missing_option in result.output


def test_schedule_defaults_to_list(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that 'mng schedule' with no subcommand defaults to 'list'."""
    no_subcommand = cli_runner.invoke(schedule, [], obj=plugin_manager)
    explicit_list = cli_runner.invoke(schedule, ["list"], obj=plugin_manager)

    assert type(no_subcommand.exception) is type(explicit_list.exception)
    assert str(no_subcommand.exception) == str(explicit_list.exception)
