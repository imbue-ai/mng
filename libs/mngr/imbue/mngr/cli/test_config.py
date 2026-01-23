"""Integration tests for the config CLI command."""

import json
from pathlib import Path

import pluggy
import pytest
from click.testing import CliRunner

from imbue.mngr.cli import config as config_module
from imbue.mngr.cli.config import config


def test_config_list_shows_merged_config(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test config list shows the merged configuration."""
    result = cli_runner.invoke(
        config,
        ["list"],
        obj=plugin_manager,
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert "prefix" in result.output


def test_config_list_with_json_format(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test config list with JSON output format."""
    result = cli_runner.invoke(
        config,
        ["list", "--format", "json"],
        obj=plugin_manager,
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    output = json.loads(result.output)
    assert "config" in output
    assert "prefix" in output["config"]


def test_config_list_with_scope_shows_file_path(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test config list with scope shows the config file path."""
    # Create a mock user config directory
    user_config_dir = tmp_path / ".config" / "mngr"
    user_config_dir.mkdir(parents=True)
    user_config_path = user_config_dir / "settings.toml"
    user_config_path.write_text('prefix = "custom-"\n')

    # Monkeypatch Path.home() to return tmp_path
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    result = cli_runner.invoke(
        config,
        ["list", "--scope", "user"],
        obj=plugin_manager,
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert "user" in result.output.lower()
    assert "prefix = custom-" in result.output


def test_config_get_retrieves_value(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test config get retrieves a specific configuration value."""
    result = cli_runner.invoke(
        config,
        ["get", "prefix"],
        obj=plugin_manager,
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    # The prefix should be the test prefix from the fixture
    assert "mngr" in result.output.lower()


def test_config_get_with_nested_key(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test config get with a nested key path."""
    result = cli_runner.invoke(
        config,
        ["get", "logging.console_level"],
        obj=plugin_manager,
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    # Console level should be one of the valid log levels
    assert any(level in result.output.upper() for level in ["INFO", "DEBUG", "WARN", "ERROR", "TRACE"])


def test_config_get_nonexistent_key_fails(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test config get with a nonexistent key returns an error."""
    result = cli_runner.invoke(
        config,
        ["get", "nonexistent.key.path"],
        obj=plugin_manager,
        catch_exceptions=False,
    )

    assert result.exit_code == 1
    assert "not found" in result.output.lower()


def test_config_get_with_json_format(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test config get with JSON output format."""
    result = cli_runner.invoke(
        config,
        ["get", "prefix", "--format", "json"],
        obj=plugin_manager,
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    output = json.loads(result.output)
    assert "key" in output
    assert output["key"] == "prefix"
    assert "value" in output


def test_config_set_creates_config_file(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test config set creates a new config file if it doesn't exist."""
    # Monkeypatch find_git_worktree_root to return our tmp_path
    monkeypatch.setattr(config_module, "find_git_worktree_root", lambda start=None: tmp_path)

    result = cli_runner.invoke(
        config,
        ["set", "prefix", "my-prefix-", "--scope", "project"],
        obj=plugin_manager,
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert "Set prefix" in result.output

    # Verify the file was created
    config_path = tmp_path / ".mngr" / "settings.toml"
    assert config_path.exists()
    content = config_path.read_text()
    assert 'prefix = "my-prefix-"' in content


def test_config_set_nested_key(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test config set with a nested key path."""
    monkeypatch.setattr(config_module, "find_git_worktree_root", lambda start=None: tmp_path)

    result = cli_runner.invoke(
        config,
        ["set", "commands.create.connect", "false", "--scope", "project"],
        obj=plugin_manager,
        catch_exceptions=False,
    )

    assert result.exit_code == 0

    # Verify the nested structure was created
    config_path = tmp_path / ".mngr" / "settings.toml"
    content = config_path.read_text()
    assert "[commands.create]" in content
    assert "connect = false" in content


def test_config_set_parses_boolean_values(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test config set correctly parses boolean values."""
    monkeypatch.setattr(config_module, "find_git_worktree_root", lambda start=None: tmp_path)

    # Set true value
    result = cli_runner.invoke(
        config,
        ["set", "test_bool", "true", "--scope", "project"],
        obj=plugin_manager,
        catch_exceptions=False,
    )
    assert result.exit_code == 0

    config_path = tmp_path / ".mngr" / "settings.toml"
    content = config_path.read_text()
    assert "test_bool = true" in content


def test_config_set_parses_integer_values(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test config set correctly parses integer values."""
    monkeypatch.setattr(config_module, "find_git_worktree_root", lambda start=None: tmp_path)

    result = cli_runner.invoke(
        config,
        ["set", "test_int", "42", "--scope", "project"],
        obj=plugin_manager,
        catch_exceptions=False,
    )
    assert result.exit_code == 0

    config_path = tmp_path / ".mngr" / "settings.toml"
    content = config_path.read_text()
    assert "test_int = 42" in content


def test_config_unset_removes_value(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test config unset removes an existing value."""
    monkeypatch.setattr(config_module, "find_git_worktree_root", lambda start=None: tmp_path)

    # First set a value
    config_dir = tmp_path / ".mngr"
    config_dir.mkdir()
    config_path = config_dir / "settings.toml"
    config_path.write_text('prefix = "test-"\nother = "keep"\n')

    # Then unset it
    result = cli_runner.invoke(
        config,
        ["unset", "prefix", "--scope", "project"],
        obj=plugin_manager,
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert "Removed prefix" in result.output

    # Verify the value was removed but other values remain
    content = config_path.read_text()
    assert "prefix" not in content
    assert "other" in content


def test_config_unset_nonexistent_key_fails(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test config unset with nonexistent key returns an error."""
    monkeypatch.setattr(config_module, "find_git_worktree_root", lambda start=None: tmp_path)

    # Create an empty config
    config_dir = tmp_path / ".mngr"
    config_dir.mkdir()
    config_path = config_dir / "settings.toml"
    config_path.write_text("")

    result = cli_runner.invoke(
        config,
        ["unset", "nonexistent", "--scope", "project"],
        obj=plugin_manager,
        catch_exceptions=False,
    )

    assert result.exit_code == 1
    assert "not found" in result.output.lower()


def test_config_path_shows_all_paths(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test config path shows all config file paths."""
    result = cli_runner.invoke(
        config,
        ["path"],
        obj=plugin_manager,
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert "user" in result.output.lower()


def test_config_path_with_scope_shows_single_path(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test config path with scope shows a single path."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    result = cli_runner.invoke(
        config,
        ["path", "--scope", "user"],
        obj=plugin_manager,
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert "settings.toml" in result.output


def test_config_path_with_json_format(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test config path with JSON output format."""
    result = cli_runner.invoke(
        config,
        ["path", "--format", "json"],
        obj=plugin_manager,
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    output = json.loads(result.output)
    assert "paths" in output
    assert len(output["paths"]) > 0


def test_config_without_subcommand_shows_help(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test config without a subcommand shows help.

    TODO: This test is intermittently failing because the implementation uses
    logger.info() to output the help text, but Click's test runner only captures
    stdout in result.output, not logger output. The logger output may or may not
    be captured depending on how the test environment is configured. To fix this
    properly, we need to either:
    1. Configure the test to capture logger output
    2. Use a different mechanism for showing help that writes to stdout
    3. Skip this test and test help display manually
    """
    result = cli_runner.invoke(
        config,
        [],
        obj=plugin_manager,
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert "Manage mngr configuration" in result.output
    assert "list" in result.output
    assert "get" in result.output
    assert "set" in result.output
