"""Unit tests for the capture CLI command."""

import pluggy
from click.testing import CliRunner

from imbue.mng.cli.capture import capture


def test_capture_no_agent_headless_fails(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Capture with no agent in headless mode should fail with a clear error."""
    result = cli_runner.invoke(
        capture,
        ["--headless"],
        obj=plugin_manager,
        catch_exceptions=True,
    )
    assert result.exit_code != 0
    assert "No agent specified" in result.output


def test_capture_full_flag_appears_in_help(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """The --full flag should appear in help output."""
    result = cli_runner.invoke(capture, ["--help"], obj=plugin_manager, catch_exceptions=False)
    assert result.exit_code == 0
    assert "--full" in result.output
    assert "scrollback" in result.output
