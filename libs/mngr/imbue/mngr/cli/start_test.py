"""Unit tests for the start CLI command."""

from unittest.mock import MagicMock

import pluggy
from click.testing import CliRunner

from imbue.mngr.cli.start import StartCliOptions
from imbue.mngr.cli.start import _send_resume_message_if_configured
from imbue.mngr.cli.start import start
from imbue.mngr.config.data_types import OutputOptions
from imbue.mngr.primitives import LogLevel
from imbue.mngr.primitives import OutputFormat


def test_start_cli_options_fields() -> None:
    """Test StartCliOptions has required fields."""
    opts = StartCliOptions(
        agents=("agent1", "agent2"),
        agent_list=("agent3",),
        start_all=False,
        dry_run=True,
        connect=False,
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
    assert opts.agents == ("agent1", "agent2")
    assert opts.agent_list == ("agent3",)
    assert opts.start_all is False
    assert opts.dry_run is True
    assert opts.connect is False


def test_start_requires_agent_or_all(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that start requires at least one agent or --all."""
    result = cli_runner.invoke(
        start,
        [],
        obj=plugin_manager,
        catch_exceptions=True,
    )

    assert result.exit_code != 0
    assert "Must specify at least one agent or use --all" in result.output


def test_start_cannot_combine_agents_and_all(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that --all cannot be combined with agent names."""
    result = cli_runner.invoke(
        start,
        ["my-agent", "--all"],
        obj=plugin_manager,
        catch_exceptions=True,
    )

    assert result.exit_code != 0
    assert "Cannot specify both agent names and --all" in result.output


def test_start_connect_requires_single_agent(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that --connect requires a single agent."""
    result = cli_runner.invoke(
        start,
        ["--all", "--connect"],
        obj=plugin_manager,
        catch_exceptions=True,
    )

    assert result.exit_code != 0
    assert "--connect can only be used with a single agent" in result.output


def test_start_connect_with_multiple_agents(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that --connect with multiple agents fails."""
    result = cli_runner.invoke(
        start,
        ["agent1", "agent2", "--connect"],
        obj=plugin_manager,
        catch_exceptions=True,
    )

    assert result.exit_code != 0
    assert "--connect can only be used with a single agent" in result.output


def test_start_nonexistent_agent(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test starting a non-existent agent."""
    result = cli_runner.invoke(
        start,
        ["nonexistent-agent-98732"],
        obj=plugin_manager,
        catch_exceptions=True,
    )

    assert result.exit_code != 0


def test_start_all_with_no_stopped_agents(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test starting all agents when none are stopped."""
    result = cli_runner.invoke(
        start,
        ["--all"],
        obj=plugin_manager,
        catch_exceptions=False,
    )

    # Should succeed but report no agents to start
    assert result.exit_code == 0
    assert "No stopped agents found to start" in result.output


def test_send_resume_message_does_nothing_when_no_message() -> None:
    """Test that _send_resume_message_if_configured does nothing when resume_message is None."""
    mock_agent = MagicMock()
    mock_agent.get_resume_message.return_value = None

    output_opts = OutputOptions(output_format=OutputFormat.HUMAN, console_level=LogLevel.INFO)

    _send_resume_message_if_configured(mock_agent, output_opts)

    mock_agent.get_resume_message.assert_called_once()
    mock_agent.send_message.assert_not_called()


def test_send_resume_message_sends_message_when_configured() -> None:
    """Test that _send_resume_message_if_configured sends the resume message when configured."""
    mock_agent = MagicMock()
    mock_agent.get_resume_message.return_value = "Welcome back!"
    # Use a very short delay for testing
    mock_agent.get_message_delay_seconds.return_value = 0.01
    mock_agent.name = "test-agent"

    output_opts = OutputOptions(output_format=OutputFormat.HUMAN, console_level=LogLevel.INFO)

    _send_resume_message_if_configured(mock_agent, output_opts)

    mock_agent.get_resume_message.assert_called_once()
    mock_agent.get_message_delay_seconds.assert_called_once()
    mock_agent.send_message.assert_called_once_with("Welcome back!")
