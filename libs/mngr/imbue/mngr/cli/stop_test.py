"""Unit tests for the stop CLI command."""

import pluggy
from click.testing import CliRunner

from imbue.mngr.cli.stop import StopCliOptions
from imbue.mngr.cli.stop import stop


def test_stop_cli_options_fields() -> None:
    """Test StopCliOptions has required fields."""
    opts = StopCliOptions(
        agents=("agent1", "agent2"),
        agent_list=("agent3",),
        stop_all=False,
        dry_run=True,
        sessions=(),
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
    assert opts.stop_all is False
    assert opts.dry_run is True
    assert opts.sessions == ()


def test_stop_requires_agent_or_all(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that stop requires at least one agent or --all."""
    result = cli_runner.invoke(
        stop,
        [],
        obj=plugin_manager,
        catch_exceptions=True,
    )

    assert result.exit_code != 0
    assert "Must specify at least one agent or use --all" in result.output


def test_stop_cannot_combine_agents_and_all(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that --all cannot be combined with agent names."""
    result = cli_runner.invoke(
        stop,
        ["my-agent", "--all"],
        obj=plugin_manager,
        catch_exceptions=True,
    )

    assert result.exit_code != 0
    assert "Cannot specify both agent names and --all" in result.output


def test_stop_nonexistent_agent(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test stopping a non-existent agent."""
    result = cli_runner.invoke(
        stop,
        ["nonexistent-agent-45721"],
        obj=plugin_manager,
        catch_exceptions=True,
    )

    assert result.exit_code != 0


def test_stop_all_with_no_running_agents(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test stopping all agents when none are running."""
    result = cli_runner.invoke(
        stop,
        ["--all"],
        obj=plugin_manager,
        catch_exceptions=False,
    )

    # Should succeed but report no agents to stop
    assert result.exit_code == 0
    assert "No running agents found to stop" in result.output


def test_stop_session_cannot_combine_with_agent_names(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that --session cannot be combined with agent names."""
    result = cli_runner.invoke(
        stop,
        ["my-agent", "--session", "mngr-some-agent"],
        obj=plugin_manager,
        catch_exceptions=True,
    )

    assert result.exit_code != 0
    assert "Cannot specify --session with agent names or --all" in result.output


def test_stop_session_cannot_combine_with_all(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that --session cannot be combined with --all."""
    result = cli_runner.invoke(
        stop,
        ["--session", "mngr-some-agent", "--all"],
        obj=plugin_manager,
        catch_exceptions=True,
    )

    assert result.exit_code != 0
    assert "Cannot specify --session with agent names or --all" in result.output


def test_stop_session_fails_with_invalid_prefix(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that --session fails when session doesn't match expected prefix format."""
    result = cli_runner.invoke(
        stop,
        ["--session", "other-session-name"],
        obj=plugin_manager,
        catch_exceptions=True,
    )

    assert result.exit_code != 0
    assert "does not match the expected format" in result.output
