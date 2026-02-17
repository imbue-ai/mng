import json
from pathlib import Path

import pluggy
import pytest
from loguru import logger

from imbue.mngr.cli.config import ConfigScope
from imbue.mngr.cli.plugin import PluginInfo
from imbue.mngr.cli.plugin import PluginSpecifierType
from imbue.mngr.cli.plugin import _build_uv_pip_install_command
from imbue.mngr.cli.plugin import _build_uv_pip_uninstall_command
from imbue.mngr.cli.plugin import _classify_plugin_specifier
from imbue.mngr.cli.plugin import _emit_plugin_add_result
from imbue.mngr.cli.plugin import _emit_plugin_list
from imbue.mngr.cli.plugin import _emit_plugin_remove_result
from imbue.mngr.cli.plugin import _emit_plugin_toggle_result
from imbue.mngr.cli.plugin import _gather_plugin_info
from imbue.mngr.cli.plugin import _get_field_value
from imbue.mngr.cli.plugin import _is_plugin_enabled
from imbue.mngr.cli.plugin import _parse_fields
from imbue.mngr.cli.plugin import _resolve_package_name_for_removal
from imbue.mngr.cli.plugin import _validate_plugin_name_is_known
from imbue.mngr.cli.plugin import _validate_pypi_specifier
from imbue.mngr.config.data_types import MngrConfig
from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.config.data_types import OutputOptions
from imbue.mngr.config.data_types import PluginConfig
from imbue.mngr.errors import PluginSpecifierError
from imbue.mngr.plugins import hookspecs
from imbue.mngr.primitives import OutputFormat
from imbue.mngr.primitives import PluginName

# =============================================================================
# Tests for PluginInfo model
# =============================================================================


def test_plugin_info_model_creates_with_all_fields() -> None:
    """PluginInfo should create with all fields provided."""
    info = PluginInfo(
        name="my-plugin",
        version="1.2.3",
        description="A test plugin",
        is_enabled=True,
    )
    assert info.name == "my-plugin"
    assert info.version == "1.2.3"
    assert info.description == "A test plugin"
    assert info.is_enabled is True


def test_plugin_info_model_defaults() -> None:
    """PluginInfo should use None defaults for optional fields."""
    info = PluginInfo(name="minimal", is_enabled=False)
    assert info.name == "minimal"
    assert info.version is None
    assert info.description is None
    assert info.is_enabled is False


# =============================================================================
# Tests for _is_plugin_enabled
# =============================================================================


def test_is_plugin_enabled_returns_true_by_default() -> None:
    """_is_plugin_enabled should return True for unknown plugins."""
    config = MngrConfig()
    assert _is_plugin_enabled("some-plugin", config) is True


def test_is_plugin_enabled_returns_false_for_disabled_plugins_set() -> None:
    """_is_plugin_enabled should return False for plugins in disabled_plugins."""
    config = MngrConfig(disabled_plugins=frozenset({"disabled-one"}))
    assert _is_plugin_enabled("disabled-one", config) is False
    assert _is_plugin_enabled("other-plugin", config) is True


def test_is_plugin_enabled_returns_false_for_config_enabled_false() -> None:
    """_is_plugin_enabled should return False for plugins with enabled=False in plugins dict."""
    config = MngrConfig(
        plugins={
            PluginName("off-plugin"): PluginConfig(enabled=False),
            PluginName("on-plugin"): PluginConfig(enabled=True),
        }
    )
    assert _is_plugin_enabled("off-plugin", config) is False
    assert _is_plugin_enabled("on-plugin", config) is True


# =============================================================================
# Tests for _get_field_value
# =============================================================================


def test_get_field_value_name() -> None:
    """_get_field_value should return name."""
    info = PluginInfo(name="test", is_enabled=True)
    assert _get_field_value(info, "name") == "test"


def test_get_field_value_version_present() -> None:
    """_get_field_value should return version when present."""
    info = PluginInfo(name="test", version="1.0", is_enabled=True)
    assert _get_field_value(info, "version") == "1.0"


def test_get_field_value_version_none() -> None:
    """_get_field_value should return '-' when version is None."""
    info = PluginInfo(name="test", is_enabled=True)
    assert _get_field_value(info, "version") == "-"


def test_get_field_value_description_present() -> None:
    """_get_field_value should return description when present."""
    info = PluginInfo(name="test", description="A plugin", is_enabled=True)
    assert _get_field_value(info, "description") == "A plugin"


def test_get_field_value_description_none() -> None:
    """_get_field_value should return '-' when description is None."""
    info = PluginInfo(name="test", is_enabled=True)
    assert _get_field_value(info, "description") == "-"


def test_get_field_value_enabled_true() -> None:
    """_get_field_value should return 'true' for enabled plugins."""
    info = PluginInfo(name="test", is_enabled=True)
    assert _get_field_value(info, "enabled") == "true"


def test_get_field_value_enabled_false() -> None:
    """_get_field_value should return 'false' for disabled plugins."""
    info = PluginInfo(name="test", is_enabled=False)
    assert _get_field_value(info, "enabled") == "false"


def test_get_field_value_unknown_field() -> None:
    """_get_field_value should return '-' for unknown fields."""
    info = PluginInfo(name="test", is_enabled=True)
    assert _get_field_value(info, "nonexistent") == "-"


# =============================================================================
# Tests for _parse_fields
# =============================================================================


def test_parse_fields_none_returns_defaults() -> None:
    """_parse_fields should return default fields when given None."""
    fields = _parse_fields(None)
    assert fields == ("name", "version", "description", "enabled")


def test_parse_fields_custom() -> None:
    """_parse_fields should parse comma-separated field names."""
    fields = _parse_fields("name,enabled")
    assert fields == ("name", "enabled")


def test_parse_fields_with_spaces() -> None:
    """_parse_fields should strip whitespace from field names."""
    fields = _parse_fields(" name , version ")
    assert fields == ("name", "version")


# =============================================================================
# Tests for _emit_plugin_list
# =============================================================================


def _make_test_plugins() -> list[PluginInfo]:
    """Create a list of test plugins."""
    return [
        PluginInfo(name="alpha", version="1.0", description="First", is_enabled=True),
        PluginInfo(name="beta", version="2.0", description="Second", is_enabled=False),
    ]


def test_emit_plugin_list_human_format_renders_table(capsys: pytest.CaptureFixture[str]) -> None:
    """_emit_plugin_list with HUMAN format should render a table via logger."""
    plugins = _make_test_plugins()
    output_opts = OutputOptions(output_format=OutputFormat.HUMAN)
    # This outputs via logger, so we just verify no exception
    _emit_plugin_list(plugins, output_opts, ("name", "version", "description", "enabled"))


def test_emit_plugin_list_human_format_empty(capsys: pytest.CaptureFixture[str]) -> None:
    """_emit_plugin_list with HUMAN format should handle empty list."""
    output_opts = OutputOptions(output_format=OutputFormat.HUMAN)
    _emit_plugin_list([], output_opts, ("name", "version", "description", "enabled"))


def test_emit_plugin_list_json_format(capsys: pytest.CaptureFixture[str]) -> None:
    """_emit_plugin_list with JSON format should output valid JSON."""
    plugins = _make_test_plugins()
    output_opts = OutputOptions(output_format=OutputFormat.JSON)
    _emit_plugin_list(plugins, output_opts, ("name", "version", "description", "enabled"))

    captured = capsys.readouterr()
    data = json.loads(captured.out.strip())
    assert "plugins" in data
    assert len(data["plugins"]) == 2
    assert data["plugins"][0]["name"] == "alpha"
    assert data["plugins"][0]["version"] == "1.0"
    assert data["plugins"][1]["name"] == "beta"
    assert data["plugins"][1]["enabled"] == "false"


def test_emit_plugin_list_jsonl_format(capsys: pytest.CaptureFixture[str]) -> None:
    """_emit_plugin_list with JSONL format should output one line per plugin."""
    plugins = _make_test_plugins()
    output_opts = OutputOptions(output_format=OutputFormat.JSONL)
    _emit_plugin_list(plugins, output_opts, ("name", "enabled"))

    captured = capsys.readouterr()
    lines = captured.out.strip().split("\n")
    assert len(lines) == 2

    first = json.loads(lines[0])
    assert first["name"] == "alpha"
    assert first["enabled"] == "true"

    second = json.loads(lines[1])
    assert second["name"] == "beta"
    assert second["enabled"] == "false"


def test_emit_plugin_list_with_field_selection(capsys: pytest.CaptureFixture[str]) -> None:
    """_emit_plugin_list should respect field selection."""
    plugins = _make_test_plugins()
    output_opts = OutputOptions(output_format=OutputFormat.JSON)
    _emit_plugin_list(plugins, output_opts, ("name", "enabled"))

    captured = capsys.readouterr()
    data = json.loads(captured.out.strip())
    # Only selected fields should appear
    assert set(data["plugins"][0].keys()) == {"name", "enabled"}


# =============================================================================
# Tests for _gather_plugin_info
# =============================================================================


def test_gather_plugin_info_returns_sorted_list() -> None:
    """_gather_plugin_info should return plugins sorted by name."""
    pm = pluggy.PluginManager("mngr")
    pm.add_hookspecs(hookspecs)

    # Register some test plugins with explicit names
    class PluginZ:
        pass

    class PluginA:
        pass

    pm.register(PluginZ(), name="zebra-plugin")
    pm.register(PluginA(), name="alpha-plugin")

    config = MngrConfig()
    mngr_ctx = MngrContext(
        config=config,
        pm=pm,
        profile_dir=_fake_profile_dir(),
    )

    plugins = _gather_plugin_info(mngr_ctx)
    names = [p.name for p in plugins]
    assert names == sorted(names)
    assert "alpha-plugin" in names
    assert "zebra-plugin" in names


def test_gather_plugin_info_reflects_disabled_status() -> None:
    """_gather_plugin_info should mark disabled plugins correctly."""
    pm = pluggy.PluginManager("mngr")
    pm.add_hookspecs(hookspecs)

    class MyPlugin:
        pass

    pm.register(MyPlugin(), name="my-plugin")

    config = MngrConfig(disabled_plugins=frozenset({"my-plugin"}))
    mngr_ctx = MngrContext(
        config=config,
        pm=pm,
        profile_dir=_fake_profile_dir(),
    )

    plugins = _gather_plugin_info(mngr_ctx)
    my_plugin = next(p for p in plugins if p.name == "my-plugin")
    assert my_plugin.is_enabled is False


def test_gather_plugin_info_skips_internal_plugins() -> None:
    """_gather_plugin_info should skip plugins with names starting with underscore."""
    pm = pluggy.PluginManager("mngr")
    pm.add_hookspecs(hookspecs)

    class InternalPlugin:
        pass

    class PublicPlugin:
        pass

    pm.register(InternalPlugin(), name="_internal")
    pm.register(PublicPlugin(), name="public-plugin")

    config = MngrConfig()
    mngr_ctx = MngrContext(
        config=config,
        pm=pm,
        profile_dir=_fake_profile_dir(),
    )

    plugins = _gather_plugin_info(mngr_ctx)
    names = [p.name for p in plugins]
    assert "_internal" not in names
    assert "public-plugin" in names


def _fake_profile_dir() -> Path:
    """Return a fake profile directory path for testing."""
    return Path("/tmp/fake-mngr-profile")


# =============================================================================
# Tests for _validate_plugin_name_is_known
# =============================================================================


def test_validate_plugin_name_is_known_no_warning_for_known() -> None:
    """_validate_plugin_name_is_known should not warn for a known plugin."""
    pm = pluggy.PluginManager("mngr")
    pm.add_hookspecs(hookspecs)

    class MyPlugin:
        pass

    pm.register(MyPlugin(), name="known-plugin")

    mngr_ctx = MngrContext(
        config=MngrConfig(),
        pm=pm,
        profile_dir=_fake_profile_dir(),
    )

    warnings: list[str] = []
    sink_id = logger.add(lambda msg: warnings.append(str(msg)), level="WARNING")
    try:
        _validate_plugin_name_is_known("known-plugin", mngr_ctx)
    finally:
        logger.remove(sink_id)

    assert not any("not currently registered" in w for w in warnings)


def test_validate_plugin_name_is_known_warns_for_unknown() -> None:
    """_validate_plugin_name_is_known should warn for an unknown plugin."""
    pm = pluggy.PluginManager("mngr")
    pm.add_hookspecs(hookspecs)

    mngr_ctx = MngrContext(
        config=MngrConfig(),
        pm=pm,
        profile_dir=_fake_profile_dir(),
    )

    warnings: list[str] = []
    sink_id = logger.add(lambda msg: warnings.append(str(msg)), level="WARNING")
    try:
        _validate_plugin_name_is_known("nonexistent-plugin", mngr_ctx)
    finally:
        logger.remove(sink_id)

    assert any("not currently registered" in w for w in warnings)


# =============================================================================
# Tests for _emit_plugin_toggle_result
# =============================================================================


def test_emit_plugin_toggle_result_json_enable(capsys: pytest.CaptureFixture[str]) -> None:
    """_emit_plugin_toggle_result should output valid JSON for enable."""
    output_opts = OutputOptions(output_format=OutputFormat.JSON)
    config_path = Path("/tmp/test/.mngr/settings.toml")

    _emit_plugin_toggle_result("modal", True, ConfigScope.PROJECT, config_path, output_opts)

    captured = capsys.readouterr()
    data = json.loads(captured.out.strip())
    assert data["plugin"] == "modal"
    assert data["enabled"] is True
    assert data["scope"] == "project"
    assert data["path"] == str(config_path)


def test_emit_plugin_toggle_result_json_disable(capsys: pytest.CaptureFixture[str]) -> None:
    """_emit_plugin_toggle_result should output valid JSON for disable."""
    output_opts = OutputOptions(output_format=OutputFormat.JSON)
    config_path = Path("/tmp/test/.mngr/settings.toml")

    _emit_plugin_toggle_result("modal", False, ConfigScope.PROJECT, config_path, output_opts)

    captured = capsys.readouterr()
    data = json.loads(captured.out.strip())
    assert data["plugin"] == "modal"
    assert data["enabled"] is False


def test_emit_plugin_toggle_result_jsonl_has_event_type(capsys: pytest.CaptureFixture[str]) -> None:
    """_emit_plugin_toggle_result with JSONL should include event type."""
    output_opts = OutputOptions(output_format=OutputFormat.JSONL)
    config_path = Path("/tmp/test/.mngr/settings.toml")

    _emit_plugin_toggle_result("modal", True, ConfigScope.PROJECT, config_path, output_opts)

    captured = capsys.readouterr()
    data = json.loads(captured.out.strip())
    assert data["event"] == "plugin_toggled"
    assert data["plugin"] == "modal"
    assert data["enabled"] is True


# =============================================================================
# Tests for _classify_plugin_specifier
# =============================================================================


def test_classify_plugin_specifier_relative_path() -> None:
    """_classify_plugin_specifier should return LOCAL_PATH for relative paths."""
    assert _classify_plugin_specifier("./my-plugin") == PluginSpecifierType.LOCAL_PATH


def test_classify_plugin_specifier_absolute_path() -> None:
    """_classify_plugin_specifier should return LOCAL_PATH for absolute paths."""
    assert _classify_plugin_specifier("/home/user/my-plugin") == PluginSpecifierType.LOCAL_PATH


def test_classify_plugin_specifier_home_path() -> None:
    """_classify_plugin_specifier should return LOCAL_PATH for tilde paths."""
    assert _classify_plugin_specifier("~/my-plugin") == PluginSpecifierType.LOCAL_PATH


def test_classify_plugin_specifier_git_url() -> None:
    """_classify_plugin_specifier should return GIT_URL for git+ URLs."""
    assert _classify_plugin_specifier("git+https://github.com/user/repo.git") == PluginSpecifierType.GIT_URL


def test_classify_plugin_specifier_pypi_package() -> None:
    """_classify_plugin_specifier should return PYPI_PACKAGE for plain package names."""
    assert _classify_plugin_specifier("mngr-opencode") == PluginSpecifierType.PYPI_PACKAGE


# =============================================================================
# Tests for _validate_pypi_specifier
# =============================================================================


def test_validate_pypi_specifier_valid_name() -> None:
    """_validate_pypi_specifier should return the package name for a valid specifier."""
    assert _validate_pypi_specifier("mngr-opencode") == "mngr-opencode"


def test_validate_pypi_specifier_name_with_version() -> None:
    """_validate_pypi_specifier should return the package name for specifiers with versions."""
    assert _validate_pypi_specifier("mngr-opencode>=1.0") == "mngr-opencode"


def test_validate_pypi_specifier_invalid_format() -> None:
    """_validate_pypi_specifier should raise PluginSpecifierError for invalid specifiers."""
    with pytest.raises(PluginSpecifierError, match="Invalid PyPI specifier"):
        _validate_pypi_specifier("not a valid!!spec$$")


# =============================================================================
# Tests for _build_uv_pip_install_command
# =============================================================================


def test_build_uv_pip_install_command_local_path() -> None:
    """_build_uv_pip_install_command should use -e flag for local paths."""
    cmd = _build_uv_pip_install_command("./my-plugin", PluginSpecifierType.LOCAL_PATH)
    assert cmd == ("uv", "pip", "install", "-e", str(Path("./my-plugin").resolve()))


def test_build_uv_pip_install_command_git_url() -> None:
    """_build_uv_pip_install_command should pass git URL directly."""
    url = "git+https://github.com/user/repo.git"
    cmd = _build_uv_pip_install_command(url, PluginSpecifierType.GIT_URL)
    assert cmd == ("uv", "pip", "install", url)


def test_build_uv_pip_install_command_pypi_package() -> None:
    """_build_uv_pip_install_command should pass package name directly."""
    cmd = _build_uv_pip_install_command("mngr-opencode", PluginSpecifierType.PYPI_PACKAGE)
    assert cmd == ("uv", "pip", "install", "mngr-opencode")


# =============================================================================
# Tests for _build_uv_pip_uninstall_command
# =============================================================================


def test_build_uv_pip_uninstall_command() -> None:
    """_build_uv_pip_uninstall_command should produce a valid uv pip uninstall command."""
    cmd = _build_uv_pip_uninstall_command("mngr-opencode")
    assert cmd == ("uv", "pip", "uninstall", "mngr-opencode")


# =============================================================================
# Tests for _resolve_package_name_for_removal
# =============================================================================


def test_resolve_package_name_for_removal_pypi_package() -> None:
    """_resolve_package_name_for_removal should return the canonical name for PyPI packages."""
    assert _resolve_package_name_for_removal("mngr-opencode>=1.0", PluginSpecifierType.PYPI_PACKAGE) == "mngr-opencode"


def test_resolve_package_name_for_removal_local_path_with_pyproject(tmp_path: Path) -> None:
    """_resolve_package_name_for_removal should read name from pyproject.toml for local paths."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "my-test-plugin"\n')

    result = _resolve_package_name_for_removal(str(tmp_path), PluginSpecifierType.LOCAL_PATH)
    assert result == "my-test-plugin"


def test_resolve_package_name_for_removal_local_path_without_pyproject(tmp_path: Path) -> None:
    """_resolve_package_name_for_removal should raise PluginSpecifierError if no pyproject.toml found."""
    with pytest.raises(PluginSpecifierError, match="No pyproject.toml found"):
        _resolve_package_name_for_removal(str(tmp_path), PluginSpecifierType.LOCAL_PATH)


def test_resolve_package_name_for_removal_git_url_raises() -> None:
    """_resolve_package_name_for_removal should raise PluginSpecifierError for git URLs."""
    with pytest.raises(PluginSpecifierError, match="Cannot determine the package name from a git URL"):
        _resolve_package_name_for_removal("git+https://github.com/user/repo.git", PluginSpecifierType.GIT_URL)


# =============================================================================
# Tests for _emit_plugin_add_result
# =============================================================================


def test_emit_plugin_add_result_json_format(capsys: pytest.CaptureFixture[str]) -> None:
    """_emit_plugin_add_result with JSON format should output valid JSON."""
    output_opts = OutputOptions(output_format=OutputFormat.JSON)
    _emit_plugin_add_result("mngr-opencode", "mngr-opencode", True, output_opts)

    captured = capsys.readouterr()
    data = json.loads(captured.out.strip())
    assert data["specifier"] == "mngr-opencode"
    assert data["package"] == "mngr-opencode"
    assert data["has_entry_points"] is True


def test_emit_plugin_add_result_jsonl_format(capsys: pytest.CaptureFixture[str]) -> None:
    """_emit_plugin_add_result with JSONL format should include event type."""
    output_opts = OutputOptions(output_format=OutputFormat.JSONL)
    _emit_plugin_add_result("./my-plugin", "my-plugin", False, output_opts)

    captured = capsys.readouterr()
    data = json.loads(captured.out.strip())
    assert data["event"] == "plugin_added"
    assert data["specifier"] == "./my-plugin"
    assert data["package"] == "my-plugin"
    assert data["has_entry_points"] is False


# =============================================================================
# Tests for _emit_plugin_remove_result
# =============================================================================


def test_emit_plugin_remove_result_json_format(capsys: pytest.CaptureFixture[str]) -> None:
    """_emit_plugin_remove_result with JSON format should output valid JSON."""
    output_opts = OutputOptions(output_format=OutputFormat.JSON)
    _emit_plugin_remove_result("mngr-opencode", output_opts)

    captured = capsys.readouterr()
    data = json.loads(captured.out.strip())
    assert data["package"] == "mngr-opencode"


def test_emit_plugin_remove_result_jsonl_format(capsys: pytest.CaptureFixture[str]) -> None:
    """_emit_plugin_remove_result with JSONL format should include event type."""
    output_opts = OutputOptions(output_format=OutputFormat.JSONL)
    _emit_plugin_remove_result("mngr-opencode", output_opts)

    captured = capsys.readouterr()
    data = json.loads(captured.out.strip())
    assert data["event"] == "plugin_removed"
    assert data["package"] == "mngr-opencode"
