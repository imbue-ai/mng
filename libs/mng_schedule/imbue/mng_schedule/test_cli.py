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
