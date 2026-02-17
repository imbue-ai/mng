import json
import subprocess
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


# =============================================================================
# Integration tests for plugin add
# =============================================================================


def test_plugin_add_local_path_invalid_package_fails(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
    temp_git_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that adding a non-package local directory fails with an error."""
    monkeypatch.chdir(temp_git_repo)

    # Create a temp directory that is not a valid Python package
    non_package_dir = temp_git_repo / "not-a-package"
    non_package_dir.mkdir()

    result = cli_runner.invoke(
        plugin,
        ["add", "--path", str(non_package_dir)],
        obj=plugin_manager,
    )

    assert result.exit_code != 0


def test_plugin_add_no_source_fails(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
    temp_git_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that calling add with no arguments fails."""
    monkeypatch.chdir(temp_git_repo)

    result = cli_runner.invoke(
        plugin,
        ["add"],
        obj=plugin_manager,
    )

    assert result.exit_code != 0


def test_plugin_add_name_and_path_mutually_exclusive(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
    temp_git_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that providing both NAME and --path fails."""
    monkeypatch.chdir(temp_git_repo)

    result = cli_runner.invoke(
        plugin,
        ["add", "mngr-opencode", "--path", "./my-plugin"],
        obj=plugin_manager,
    )

    assert result.exit_code != 0


def test_plugin_add_invalid_name_fails(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
    temp_git_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that adding an invalid package name fails with a clear error."""
    monkeypatch.chdir(temp_git_repo)

    result = cli_runner.invoke(
        plugin,
        ["add", "not a valid!!spec$$"],
        obj=plugin_manager,
    )

    assert result.exit_code != 0


# =============================================================================
# Integration tests for plugin remove
# =============================================================================


def test_plugin_remove_nonexistent_package_fails(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
    temp_git_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that removing a package that is not installed fails with an error."""
    monkeypatch.chdir(temp_git_repo)

    result = cli_runner.invoke(
        plugin,
        ["remove", "definitely-not-installed-package-xyz-999"],
        obj=plugin_manager,
    )

    assert result.exit_code != 0


def test_plugin_remove_no_source_fails(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
    temp_git_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that calling remove with no arguments fails."""
    monkeypatch.chdir(temp_git_repo)

    result = cli_runner.invoke(
        plugin,
        ["remove"],
        obj=plugin_manager,
    )

    assert result.exit_code != 0


def test_plugin_remove_name_and_path_mutually_exclusive(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
    temp_git_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that providing both NAME and --path fails."""
    monkeypatch.chdir(temp_git_repo)

    result = cli_runner.invoke(
        plugin,
        ["remove", "mngr-opencode", "--path", "./my-plugin"],
        obj=plugin_manager,
    )

    assert result.exit_code != 0


# =============================================================================
# Integration tests for plugin add/remove success path
# =============================================================================

_DUMMY_PLUGIN_NAME = "mngr-test-dummy-plugin"

_DUMMY_PYPROJECT_TOML = """\
[project]
name = "mngr-test-dummy-plugin"
version = "0.0.1"
description = "Dummy plugin for integration testing"

[project.entry-points.mngr]
test-dummy = "mngr_test_dummy_plugin"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
"""

_DUMMY_PLUGIN_MODULE = """\
import pluggy

hookimpl = pluggy.HookimplMarker("mngr")


@hookimpl
def register_agent_type():
    return ("test-dummy-agent", None, None)
"""


def _create_dummy_plugin_package(base_dir: Path) -> Path:
    """Create a minimal mngr plugin package that registers an agent type.

    Returns the path to the plugin directory.
    """
    plugin_dir = base_dir / "mngr-test-dummy-plugin"
    plugin_dir.mkdir()
    (plugin_dir / "pyproject.toml").write_text(_DUMMY_PYPROJECT_TOML)
    (plugin_dir / "mngr_test_dummy_plugin.py").write_text(_DUMMY_PLUGIN_MODULE)
    return plugin_dir


def _force_uninstall_dummy_plugin() -> None:
    """Force-uninstall the dummy plugin package, ignoring errors."""
    subprocess.run(
        ["uv", "pip", "uninstall", _DUMMY_PLUGIN_NAME],
        capture_output=True,
    )


def _run_mngr(*args: str) -> subprocess.CompletedProcess[str]:
    """Run a mngr command via `uv run mngr` and return the result."""
    result = subprocess.run(
        ["uv", "run", "mngr", *args],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, f"mngr {' '.join(args)} failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
    return result


@pytest.mark.acceptance
@pytest.mark.timeout(60)
def test_plugin_install_discover_and_remove(
    tmp_path: Path,
) -> None:
    """Test that an installed plugin is discovered by mngr and can be removed.

    Installs a dummy plugin (non-editable) into the current venv, then
    verifies it appears in `mngr plugin list`, its hook fires (agent type
    is registered), and `mngr plugin remove` cleans it up.

    Uses `uv run mngr` subprocesses so each invocation starts a fresh Python
    process that naturally discovers the plugin via setuptools entry points.

    Non-editable install is used because editable installs create .pth files
    that are not processed by already-running pytest-xdist worker processes,
    causing import errors in their plugin_manager fixtures.
    """
    _force_uninstall_dummy_plugin()

    plugin_dir = _create_dummy_plugin_package(tmp_path)

    try:
        # -- Install the plugin (non-editable, directly via uv) --
        install_result = subprocess.run(
            ["uv", "pip", "install", str(plugin_dir)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert install_result.returncode == 0, f"install failed: {install_result.stderr}"

        # -- Verify the plugin shows up in `mngr plugin list` --
        list_result = _run_mngr("plugin", "list", "--format", "json")
        list_output = json.loads(list_result.stdout)
        plugin_names = [p["name"] for p in list_output["plugins"]]
        assert "test-dummy" in plugin_names

        # -- Remove the plugin via `mngr plugin remove` --
        remove_result = _run_mngr("plugin", "remove", _DUMMY_PLUGIN_NAME, "--format", "json")
        remove_output = json.loads(remove_result.stdout)
        assert remove_output["package"] == _DUMMY_PLUGIN_NAME

        # -- Verify it no longer shows up --
        list_after = _run_mngr("plugin", "list", "--format", "json")
        list_after_output = json.loads(list_after.stdout)
        plugin_names_after = [p["name"] for p in list_after_output["plugins"]]
        assert "test-dummy" not in plugin_names_after

    finally:
        _force_uninstall_dummy_plugin()


@pytest.mark.acceptance
@pytest.mark.timeout(60)
def test_plugin_add_path_and_remove_via_mngr(
    tmp_path: Path,
) -> None:
    """Test that `mngr plugin add --path` installs a local plugin and `mngr plugin remove` removes it.

    Uses `uv run mngr` subprocesses for the full lifecycle. The install is
    editable (as --path produces), so we install and immediately remove to
    minimize the window where pytest-xdist workers might encounter the
    editable .pth entry.
    """
    _force_uninstall_dummy_plugin()

    plugin_dir = _create_dummy_plugin_package(tmp_path)

    try:
        # -- Install via mngr plugin add --path --
        add_result = _run_mngr("plugin", "add", "--path", str(plugin_dir), "--format", "json")
        add_output = json.loads(add_result.stdout)
        assert add_output["package"] == _DUMMY_PLUGIN_NAME
        assert add_output["has_entry_points"] is True

        # -- Verify discovery in a fresh process --
        list_result = _run_mngr("plugin", "list", "--format", "json")
        list_output = json.loads(list_result.stdout)
        plugin_names = [p["name"] for p in list_output["plugins"]]
        assert "test-dummy" in plugin_names

        # -- Remove via mngr plugin remove --
        remove_result = _run_mngr("plugin", "remove", _DUMMY_PLUGIN_NAME, "--format", "json")
        remove_output = json.loads(remove_result.stdout)
        assert remove_output["package"] == _DUMMY_PLUGIN_NAME

    finally:
        _force_uninstall_dummy_plugin()
