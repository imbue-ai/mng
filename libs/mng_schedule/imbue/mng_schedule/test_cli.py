"""Integration tests for the schedule CLI command."""

import pluggy
from click.testing import CliRunner

from imbue.mng_schedule.cli import schedule


def test_schedule_add_raises_not_implemented(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that schedule add raises NotImplementedError (not a different error)."""
    result = cli_runner.invoke(
        schedule,
        [
            "add",
            "--command",
            "create",
            "--schedule",
            "0 2 * * *",
            "--provider",
            "local",
        ],
        obj=plugin_manager,
    )
    assert result.exit_code != 0
    assert result.exception is not None
    assert isinstance(result.exception, NotImplementedError)
    assert "schedule add is not implemented yet" in str(result.exception)


def test_schedule_add_missing_required_options(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that schedule add fails with usage error when required options are missing."""
    result = cli_runner.invoke(
        schedule,
        ["add"],
        obj=plugin_manager,
    )
    assert result.exit_code != 0
    assert "Missing" in result.output or "required" in result.output.lower() or "Error" in result.output
