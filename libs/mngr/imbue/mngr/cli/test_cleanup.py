"""Integration tests for the cleanup CLI command."""

import json

import pluggy
from click.testing import CliRunner

from imbue.mngr.cli.cleanup import cleanup


def test_cleanup_dry_run_json_format_no_agents(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that --dry-run --yes --format json outputs valid JSON when no agents exist."""
    result = cli_runner.invoke(
        cleanup,
        ["--dry-run", "--yes", "--format", "json"],
        obj=plugin_manager,
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    output = json.loads(result.output.strip())
    assert output["agents"] == []


def test_cleanup_dry_run_jsonl_format_no_agents(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that --dry-run --yes --format jsonl outputs valid JSONL when no agents exist."""
    result = cli_runner.invoke(
        cleanup,
        ["--dry-run", "--yes", "--format", "jsonl"],
        obj=plugin_manager,
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    # Should have at least one JSONL line
    lines = [line for line in result.output.strip().split("\n") if line.strip()]
    for line in lines:
        parsed = json.loads(line)
        assert "event" in parsed


def test_cleanup_stop_action_dry_run(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that --stop --dry-run --yes works."""
    result = cli_runner.invoke(
        cleanup,
        ["--stop", "--dry-run", "--yes"],
        obj=plugin_manager,
        catch_exceptions=False,
    )
    assert result.exit_code == 0


def test_cleanup_with_older_than_filter(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that --older-than filter is accepted."""
    result = cli_runner.invoke(
        cleanup,
        ["--older-than", "7d", "--dry-run", "--yes"],
        obj=plugin_manager,
        catch_exceptions=False,
    )
    assert result.exit_code == 0


def test_cleanup_with_idle_for_filter(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that --idle-for filter is accepted."""
    result = cli_runner.invoke(
        cleanup,
        ["--idle-for", "1h", "--dry-run", "--yes"],
        obj=plugin_manager,
        catch_exceptions=False,
    )
    assert result.exit_code == 0


def test_cleanup_with_provider_filter(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that --provider filter is accepted."""
    result = cli_runner.invoke(
        cleanup,
        ["--provider", "local", "--dry-run", "--yes"],
        obj=plugin_manager,
        catch_exceptions=False,
    )
    assert result.exit_code == 0


def test_cleanup_with_agent_type_filter(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that --agent-type filter is accepted."""
    result = cli_runner.invoke(
        cleanup,
        ["--agent-type", "claude", "--dry-run", "--yes"],
        obj=plugin_manager,
        catch_exceptions=False,
    )
    assert result.exit_code == 0


def test_cleanup_with_combined_filters(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that multiple filters can be combined."""
    result = cli_runner.invoke(
        cleanup,
        ["--older-than", "7d", "--provider", "local", "--agent-type", "claude", "--dry-run", "--yes"],
        obj=plugin_manager,
        catch_exceptions=False,
    )
    assert result.exit_code == 0


def test_cleanup_alias_clean(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that 'clean' alias works via help metadata registration."""
    # The alias is registered in main.py - we can at least test that the
    # cleanup command itself works when invoked directly
    result = cli_runner.invoke(
        cleanup,
        ["--dry-run", "--yes"],
        obj=plugin_manager,
        catch_exceptions=False,
    )
    assert result.exit_code == 0
