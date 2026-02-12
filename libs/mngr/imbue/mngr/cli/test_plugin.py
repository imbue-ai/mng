"""Integration tests for the plugin CLI command."""

import json

import pluggy
from click.testing import CliRunner

from imbue.mngr.cli.plugin import plugin


def test_plugin_list_succeeds(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that plugin list executes without errors."""
    result = cli_runner.invoke(
        plugin,
        ["list"],
        obj=plugin_manager,
        catch_exceptions=False,
    )

    assert result.exit_code == 0


def test_plugin_list_json_format_returns_valid_json(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that plugin list with --format json produces valid JSON output."""
    result = cli_runner.invoke(
        plugin,
        ["list", "--format", "json"],
        obj=plugin_manager,
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    output = json.loads(result.output)
    assert "plugins" in output
    assert isinstance(output["plugins"], list)


def test_plugin_list_json_format_contains_expected_fields(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that plugin list JSON output includes all default fields."""
    result = cli_runner.invoke(
        plugin,
        ["list", "--format", "json"],
        obj=plugin_manager,
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    output = json.loads(result.output)
    for plugin_entry in output["plugins"]:
        assert "name" in plugin_entry
        assert "version" in plugin_entry
        assert "description" in plugin_entry
        assert "enabled" in plugin_entry


def test_plugin_list_with_fields_limits_output(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that --fields limits which fields appear in JSON output."""
    result = cli_runner.invoke(
        plugin,
        ["list", "--format", "json", "--fields", "name,enabled"],
        obj=plugin_manager,
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    output = json.loads(result.output)
    for plugin_entry in output["plugins"]:
        assert set(plugin_entry.keys()) == {"name", "enabled"}


def test_plugin_list_active_filters_to_enabled_only(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that --active filters to only enabled plugins."""
    result = cli_runner.invoke(
        plugin,
        ["list", "--active", "--format", "json"],
        obj=plugin_manager,
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    output = json.loads(result.output)
    for plugin_entry in output["plugins"]:
        assert plugin_entry["enabled"] == "true"


def test_plugin_list_jsonl_format_outputs_one_line_per_plugin(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that plugin list with --format jsonl outputs one JSON line per plugin."""
    result = cli_runner.invoke(
        plugin,
        ["list", "--format", "jsonl"],
        obj=plugin_manager,
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    lines = [line for line in result.output.strip().split("\n") if line.strip()]
    for line in lines:
        parsed = json.loads(line)
        assert "name" in parsed


def test_plugin_without_subcommand_shows_help(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that invoking plugin with no subcommand shows help text."""
    result = cli_runner.invoke(
        plugin,
        [],
        obj=plugin_manager,
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert "list" in result.output.lower()
