import json
from pathlib import Path

import pluggy
import pytest
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
    """Test that invoking plugin with no subcommand shows help text.

    Help output goes through show_help_with_pager, which writes to stdout
    in non-interactive mode (as used by CliRunner).
    """
    result = cli_runner.invoke(
        plugin,
        [],
        obj=plugin_manager,
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert "list" in result.output.lower()


# =============================================================================
# Integration tests for plugin enable
# =============================================================================


def test_plugin_enable_writes_enabled_true_to_project_toml(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
    temp_git_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    mngr_test_root_name: str,
) -> None:
    """Test that plugin enable writes enabled = true to project settings."""
    monkeypatch.chdir(temp_git_repo)

    result = cli_runner.invoke(
        plugin,
        ["enable", "modal"],
        obj=plugin_manager,
        catch_exceptions=False,
    )

    assert result.exit_code == 0

    config_path = temp_git_repo / f".{mngr_test_root_name}" / "settings.toml"
    assert config_path.exists()
    content = config_path.read_text()
    assert "enabled = true" in content


def test_plugin_disable_writes_enabled_false_to_project_toml(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
    temp_git_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    mngr_test_root_name: str,
) -> None:
    """Test that plugin disable writes enabled = false to project settings."""
    monkeypatch.chdir(temp_git_repo)

    result = cli_runner.invoke(
        plugin,
        ["disable", "modal"],
        obj=plugin_manager,
        catch_exceptions=False,
    )

    assert result.exit_code == 0

    config_path = temp_git_repo / f".{mngr_test_root_name}" / "settings.toml"
    assert config_path.exists()
    content = config_path.read_text()
    assert "enabled = false" in content


def test_plugin_enable_json_format_returns_valid_json(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
    temp_git_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that plugin enable with --format json returns valid JSON."""
    monkeypatch.chdir(temp_git_repo)

    result = cli_runner.invoke(
        plugin,
        ["enable", "opencode", "--format", "json"],
        obj=plugin_manager,
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    output = json.loads(result.output)
    assert output["plugin"] == "opencode"
    assert output["enabled"] is True
    assert output["scope"] == "project"
    assert "path" in output


def test_plugin_enable_default_scope_is_project(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
    temp_git_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that plugin enable defaults to project scope."""
    monkeypatch.chdir(temp_git_repo)

    result = cli_runner.invoke(
        plugin,
        ["enable", "opencode", "--format", "json"],
        obj=plugin_manager,
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    output = json.loads(result.output)
    assert output["scope"] == "project"


def test_plugin_enable_registered_plugin_does_not_warn(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
    temp_git_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that enabling a registered plugin does not produce an unregistered warning.

    Built-in plugins are registered with short names (e.g. "local", "claude")
    so that 'mngr plugin enable <name>' works without warnings. This test
    verifies the names used in the docs examples resolve correctly.
    """
    monkeypatch.chdir(temp_git_repo)

    # These are the built-in plugin names that are registered by the test fixture
    # (local, ssh from load_local_backend_only; claude, codex from load_agents_from_plugins)
    for name in ("local", "ssh", "claude", "codex"):
        result = cli_runner.invoke(
            plugin,
            ["enable", name],
            obj=plugin_manager,
            catch_exceptions=False,
        )

        assert result.exit_code == 0
        assert "not currently registered" not in result.output, (
            f"Plugin '{name}' should be registered but got warning: {result.output}"
        )


def test_plugin_enable_unknown_plugin_warns_but_succeeds(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
    temp_git_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    mngr_test_root_name: str,
) -> None:
    """Test that enabling an unknown plugin warns but still writes config."""
    monkeypatch.chdir(temp_git_repo)

    result = cli_runner.invoke(
        plugin,
        ["enable", "nonexistent-plugin"],
        obj=plugin_manager,
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert "not currently registered" in result.output

    config_path = temp_git_repo / f".{mngr_test_root_name}" / "settings.toml"
    assert config_path.exists()
    content = config_path.read_text()
    assert "enabled = true" in content
