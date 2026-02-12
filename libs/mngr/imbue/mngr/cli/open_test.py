"""Unit tests for the open CLI command."""

import pluggy
from click.testing import CliRunner

from imbue.mngr.cli.open import OpenCliOptions
from imbue.mngr.cli.open import open_command


def test_open_cli_options_fields() -> None:
    """Test OpenCliOptions has required fields."""
    opts = OpenCliOptions(
        agent="my-agent",
        url_type=None,
        start=True,
        wait=False,
        active=False,
        output_format="human",
        quiet=False,
        verbose=0,
        log_file=None,
        log_commands=None,
        log_command_output=None,
        log_env_vars=None,
        project_context_path=None,
        plugin=(),
        disable_plugin=(),
    )
    assert opts.agent == "my-agent"
    assert opts.url_type is None
    assert opts.start is True
    assert opts.wait is False
    assert opts.active is False


def test_open_cli_options_with_all_fields() -> None:
    """Test OpenCliOptions with all fields populated."""
    opts = OpenCliOptions(
        agent="test-agent",
        url_type="terminal",
        start=False,
        wait=True,
        active=True,
        output_format="json",
        quiet=True,
        verbose=2,
        log_file="/tmp/test.log",
        log_commands=True,
        log_command_output=True,
        log_env_vars=False,
        project_context_path="/tmp/project",
        plugin=("my-plugin",),
        disable_plugin=("other-plugin",),
    )
    assert opts.agent == "test-agent"
    assert opts.url_type == "terminal"
    assert opts.start is False
    assert opts.wait is True
    assert opts.active is True


def test_open_type_raises_not_implemented(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that specifying a URL type raises NotImplementedError."""
    # Use positional args: agent="my-agent", url_type="terminal"
    result = cli_runner.invoke(
        open_command,
        ["my-agent", "terminal"],
        obj=plugin_manager,
        catch_exceptions=True,
    )

    assert result.exit_code != 0
    assert isinstance(result.exception, NotImplementedError)
    assert "--type is not implemented yet" in str(result.exception)


def test_open_active_without_wait_raises_error(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that --active without --wait raises an error."""
    result = cli_runner.invoke(
        open_command,
        ["my-agent", "--active"],
        obj=plugin_manager,
        catch_exceptions=True,
    )

    assert result.exit_code != 0
    assert "--active requires --wait" in result.output
