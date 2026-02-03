"""Tests for config loader."""

from pathlib import Path
from typing import Any

import click
import pluggy
import pytest

from imbue.mngr.config.data_types import CommandDefaults
from imbue.mngr.config.data_types import LoggingConfig
from imbue.mngr.config.data_types import PluginConfig
from imbue.mngr.config.data_types import get_or_create_user_id
from imbue.mngr.config.loader import _apply_plugin_overrides
from imbue.mngr.config.loader import _get_local_config_name
from imbue.mngr.config.loader import _get_project_config_name
from imbue.mngr.config.loader import _get_user_config_path
from imbue.mngr.config.loader import _load_toml
from imbue.mngr.config.loader import _merge_command_defaults
from imbue.mngr.config.loader import _parse_agent_types
from imbue.mngr.config.loader import _parse_command_env_vars
from imbue.mngr.config.loader import _parse_commands
from imbue.mngr.config.loader import _parse_config
from imbue.mngr.config.loader import _parse_logging_config
from imbue.mngr.config.loader import _parse_plugins
from imbue.mngr.config.loader import _parse_providers
from imbue.mngr.config.loader import get_or_create_profile_dir
from imbue.mngr.config.loader import load_config
from imbue.mngr.errors import ConfigNotFoundError
from imbue.mngr.errors import ConfigParseError
from imbue.mngr.main import cli
from imbue.mngr.plugins import hookspecs
from imbue.mngr.primitives import AgentTypeName
from imbue.mngr.primitives import LogLevel
from imbue.mngr.primitives import PluginName
from imbue.mngr.primitives import ProviderBackendName
from imbue.mngr.primitives import ProviderInstanceName
from imbue.mngr.providers.registry import load_all_registries

hookimpl = pluggy.HookimplMarker("mngr")

# =============================================================================
# Tests for _parse_command_env_vars
# =============================================================================


def test_parse_command_env_vars_single_param() -> None:
    """Test parsing a single command param from env var."""
    environ = {"MNGR_COMMANDS_CREATE_NEW_BRANCH_PREFIX": "agent/"}
    result = _parse_command_env_vars(environ)

    assert "create" in result
    assert result["create"].defaults["new_branch_prefix"] == "agent/"


def test_parse_command_env_vars_multiple_params_same_command() -> None:
    """Test parsing multiple params for the same command."""
    environ = {
        "MNGR_COMMANDS_CREATE_NEW_BRANCH_PREFIX": "agent/",
        "MNGR_COMMANDS_CREATE_CONNECT": "false",
    }
    result = _parse_command_env_vars(environ)

    assert "create" in result
    assert result["create"].defaults["new_branch_prefix"] == "agent/"
    # Values are kept as strings - type conversion happens in click/pydantic
    assert result["create"].defaults["connect"] == "false"


def test_parse_command_env_vars_multiple_commands() -> None:
    """Test parsing params for different commands."""
    environ = {
        "MNGR_COMMANDS_CREATE_NAME": "myagent",
        "MNGR_COMMANDS_LIST_FORMAT": "json",
    }
    result = _parse_command_env_vars(environ)

    assert "create" in result
    assert result["create"].defaults["name"] == "myagent"
    assert "list" in result
    assert result["list"].defaults["format"] == "json"


def test_parse_command_env_vars_ignores_non_matching_vars() -> None:
    """Test that non-matching env vars are ignored."""
    environ = {
        "MNGR_COMMANDS_CREATE_NAME": "myagent",
        "MNGR_PREFIX": "test-",
        "PATH": "/usr/bin",
        "HOME": "/home/user",
    }
    result = _parse_command_env_vars(environ)

    assert "create" in result
    assert len(result) == 1


def test_parse_command_env_vars_ignores_no_underscore_after_command() -> None:
    """Test that vars without underscore after command prefix are ignored."""
    environ = {"MNGR_COMMANDS_CREATE": "ignored"}
    result = _parse_command_env_vars(environ)

    assert len(result) == 0


def test_parse_command_env_vars_lowercases_command_and_param() -> None:
    """Test that command and param names are lowercased."""
    environ = {"MNGR_COMMANDS_CREATE_NEW_BRANCH_PREFIX": "agent/"}
    result = _parse_command_env_vars(environ)

    assert "create" in result
    assert "new_branch_prefix" in result["create"].defaults


def test_parse_command_env_vars_empty_environ() -> None:
    """Test parsing empty environ returns empty dict."""
    result = _parse_command_env_vars({})
    assert result == {}


def test_parse_command_env_vars_preserves_values_as_strings() -> None:
    """Test that all values are preserved as strings.

    Type conversion happens downstream in click/pydantic where the
    actual type information is available.
    """
    environ = {
        "MNGR_COMMANDS_CREATE_CONNECT": "true",
        "MNGR_COMMANDS_CREATE_RETRY": "5",
        "MNGR_COMMANDS_CREATE_NAME": "myagent",
    }
    result = _parse_command_env_vars(environ)

    # All values should be strings
    assert result["create"].defaults["connect"] == "true"
    assert result["create"].defaults["retry"] == "5"
    assert result["create"].defaults["name"] == "myagent"
    assert all(isinstance(v, str) for v in result["create"].defaults.values())


# =============================================================================
# Tests for _merge_command_defaults
# =============================================================================


def test_merge_command_defaults_empty_base() -> None:
    """Test merging into empty base."""
    base: dict[str, CommandDefaults] = {}
    override = {"create": CommandDefaults(defaults={"name": "test"})}
    result = _merge_command_defaults(base, override)

    assert "create" in result
    assert result["create"].defaults["name"] == "test"


def test_merge_command_defaults_empty_override() -> None:
    """Test merging empty override."""
    base = {"create": CommandDefaults(defaults={"name": "test"})}
    override: dict[str, CommandDefaults] = {}
    result = _merge_command_defaults(base, override)

    assert "create" in result
    assert result["create"].defaults["name"] == "test"


def test_merge_command_defaults_combines_different_commands() -> None:
    """Test merging with different commands."""
    base = {"create": CommandDefaults(defaults={"name": "test"})}
    override = {"list": CommandDefaults(defaults={"format": "json"})}
    result = _merge_command_defaults(base, override)

    assert "create" in result
    assert "list" in result


def test_merge_command_defaults_override_wins_same_command() -> None:
    """Test that override wins for same command params."""
    base = {"create": CommandDefaults(defaults={"name": "old", "other": "base"})}
    override = {"create": CommandDefaults(defaults={"name": "new"})}
    result = _merge_command_defaults(base, override)

    assert result["create"].defaults["name"] == "new"
    assert result["create"].defaults["other"] == "base"


# =============================================================================
# Test for single-word command names
# =============================================================================


def test_all_cli_commands_are_single_word() -> None:
    """Ensure all CLI command names are single words (no spaces, hyphens, or underscores).

    This is CRITICAL for the MNGR_COMMANDS_<COMMANDNAME>_<PARAMNAME> env var parsing
    to work correctly. If command names contained underscores, parsing would be ambiguous.

    For example, if a command was named "foo_bar" and a param was "baz", the env var
    would be "MNGR_COMMANDS_FOO_BAR_BAZ", which could be interpreted as either:
        - command="foo", param="bar_baz"
        - command="foo_bar", param="baz"

    By requiring single-word commands, we avoid this ambiguity.

    Any future plugins that register custom commands MUST also follow this convention.
    """
    # Get all commands from the CLI group
    assert isinstance(cli, click.Group), "cli should be a click.Group"

    invalid_commands = []
    for command_name in cli.commands.keys():
        # Check for spaces, hyphens, or underscores in command names
        if " " in command_name or "-" in command_name or "_" in command_name:
            invalid_commands.append(command_name)

    assert not invalid_commands, (
        f"CLI command names must be single words (no spaces, hyphens, or underscores) "
        f"for MNGR_COMMANDS_<COMMANDNAME>_<PARAMNAME> env var parsing to work. "
        f"Invalid commands: {invalid_commands}"
    )


# =============================================================================
# Tests for config file path functions
# =============================================================================


def test_get_user_config_path_returns_correct_path() -> None:
    """_get_user_config_path should return settings.toml in profile directory."""
    profile_dir = Path("/home/user/.mngr/profiles/abc123")
    path = _get_user_config_path(profile_dir)
    assert path == profile_dir / "settings.toml"


def test_get_project_config_name_returns_correct_path() -> None:
    """_get_project_config_name should return correct relative path."""
    path = _get_project_config_name("mngr")
    assert path == Path(".mngr") / "settings.toml"


def test_get_local_config_name_returns_correct_path() -> None:
    """_get_local_config_name should return correct relative path."""
    path = _get_local_config_name("mngr")
    assert path == Path(".mngr") / "settings.local.toml"


# =============================================================================
# Tests for _load_toml
# =============================================================================


def test_load_toml_raises_config_not_found(tmp_path: Path) -> None:
    """_load_toml should raise ConfigNotFoundError for missing file."""
    with pytest.raises(ConfigNotFoundError):
        _load_toml(tmp_path / "nonexistent.toml")


def test_load_toml_raises_config_parse_error(tmp_path: Path) -> None:
    """_load_toml should raise ConfigParseError for invalid TOML."""
    invalid_toml = tmp_path / "invalid.toml"
    invalid_toml.write_text("[invalid toml syntax")
    with pytest.raises(ConfigParseError):
        _load_toml(invalid_toml)


def test_load_toml_parses_valid_file(tmp_path: Path) -> None:
    """_load_toml should parse valid TOML files."""
    valid_toml = tmp_path / "valid.toml"
    valid_toml.write_text('prefix = "test-"\n[agent_types.claude]\ncommand = "claude"')
    result = _load_toml(valid_toml)
    assert result["prefix"] == "test-"
    assert result["agent_types"]["claude"]["command"] == "claude"


# =============================================================================
# Tests for _parse_providers
# =============================================================================


def test_parse_providers_parses_valid_provider() -> None:
    """_parse_providers should parse valid provider configs."""
    raw = {"my-local": {"backend": "local"}}
    result = _parse_providers(raw)
    assert ProviderInstanceName("my-local") in result
    assert result[ProviderInstanceName("my-local")].backend == ProviderBackendName("local")


def test_parse_providers_raises_on_missing_backend() -> None:
    """_parse_providers should raise ConfigParseError for missing backend."""
    raw = {"my-provider": {"some_field": "value"}}
    with pytest.raises(ConfigParseError, match="missing required 'backend'"):
        _parse_providers(raw)


# =============================================================================
# Tests for _parse_agent_types
# =============================================================================


def test_parse_agent_types_parses_valid_agent() -> None:
    """_parse_agent_types should parse valid agent type configs."""
    raw = {"claude": {"cli_args": "--verbose"}}
    result = _parse_agent_types(raw)
    assert AgentTypeName("claude") in result
    assert result[AgentTypeName("claude")].cli_args == "--verbose"


def test_parse_agent_types_handles_empty_dict() -> None:
    """_parse_agent_types should handle empty dict."""
    result = _parse_agent_types({})
    assert result == {}


# =============================================================================
# Tests for _parse_plugins
# =============================================================================


def test_parse_plugins_parses_valid_plugin() -> None:
    """_parse_plugins should parse valid plugin configs."""
    raw = {"my-plugin": {"enabled": True}}
    result = _parse_plugins(raw)
    assert PluginName("my-plugin") in result
    assert result[PluginName("my-plugin")].enabled is True


def test_parse_plugins_handles_empty_dict() -> None:
    """_parse_plugins should handle empty dict."""
    result = _parse_plugins({})
    assert result == {}


# =============================================================================
# Tests for _apply_plugin_overrides
# =============================================================================


def test_apply_plugin_overrides_enables_plugins() -> None:
    """_apply_plugin_overrides should enable plugins."""
    plugins: dict[PluginName, PluginConfig] = {}
    result, disabled = _apply_plugin_overrides(plugins, enabled_plugins=["my-plugin"], disabled_plugins=None)
    assert PluginName("my-plugin") in result
    assert result[PluginName("my-plugin")].enabled is True
    assert len(disabled) == 0


def test_apply_plugin_overrides_disables_plugins() -> None:
    """_apply_plugin_overrides should disable and filter out plugins."""
    plugins = {PluginName("my-plugin"): PluginConfig(enabled=True)}
    result, disabled = _apply_plugin_overrides(plugins, enabled_plugins=None, disabled_plugins=["my-plugin"])
    # Disabled plugins are filtered out
    assert PluginName("my-plugin") not in result
    assert "my-plugin" in disabled


def test_apply_plugin_overrides_filters_disabled_plugins() -> None:
    """_apply_plugin_overrides should filter out disabled plugins."""
    plugins = {
        PluginName("enabled-plugin"): PluginConfig(enabled=True),
        PluginName("disabled-plugin"): PluginConfig(enabled=False),
    }
    result, disabled = _apply_plugin_overrides(plugins, enabled_plugins=None, disabled_plugins=None)
    assert PluginName("enabled-plugin") in result
    assert PluginName("disabled-plugin") not in result
    assert "disabled-plugin" in disabled


def test_apply_plugin_overrides_enables_existing_plugin() -> None:
    """_apply_plugin_overrides should enable existing disabled plugins."""
    plugins = {PluginName("my-plugin"): PluginConfig(enabled=False)}
    result, disabled = _apply_plugin_overrides(plugins, enabled_plugins=["my-plugin"], disabled_plugins=None)
    assert PluginName("my-plugin") in result
    assert result[PluginName("my-plugin")].enabled is True
    assert "my-plugin" not in disabled


def test_apply_plugin_overrides_creates_disabled_plugin() -> None:
    """_apply_plugin_overrides should create new disabled plugins."""
    plugins: dict[PluginName, PluginConfig] = {}
    result, disabled = _apply_plugin_overrides(plugins, enabled_plugins=None, disabled_plugins=["new-plugin"])
    # Disabled plugins are filtered out, so should not be in result
    assert PluginName("new-plugin") not in result
    assert "new-plugin" in disabled


# =============================================================================
# Tests for _parse_logging_config
# =============================================================================


def test_parse_logging_config_parses_valid_config() -> None:
    """_parse_logging_config should parse valid logging config."""
    raw = {"file_level": "TRACE", "max_log_files": 500}
    result = _parse_logging_config(raw)
    assert isinstance(result, LoggingConfig)
    assert result.file_level == LogLevel.TRACE
    assert result.max_log_files == 500


def test_parse_logging_config_handles_empty_dict() -> None:
    """_parse_logging_config should handle empty dict."""
    result = _parse_logging_config({})
    assert isinstance(result, LoggingConfig)


# =============================================================================
# Tests for _parse_commands
# =============================================================================


def test_parse_commands_parses_valid_commands() -> None:
    """_parse_commands should parse valid command defaults."""
    raw = {"create": {"name": "test-agent", "connect": False}}
    result = _parse_commands(raw)
    assert "create" in result
    assert result["create"].defaults["name"] == "test-agent"
    assert result["create"].defaults["connect"] is False


def test_parse_commands_handles_empty_dict() -> None:
    """_parse_commands should handle empty dict."""
    result = _parse_commands({})
    assert result == {}


# =============================================================================
# Tests for _parse_config
# =============================================================================


def test_parse_config_parses_full_config() -> None:
    """_parse_config should parse a full config dict."""
    raw = {
        "prefix": "test-",
        "default_host_dir": "/tmp/test",
        "agent_types": {"claude": {"cli_args": "--verbose"}},
        "providers": {"local": {"backend": "local"}},
        "plugins": {"my-plugin": {"enabled": True}},
        "commands": {"create": {"name": "test"}},
        "logging": {"file_level": "DEBUG"},
    }
    result = _parse_config(raw)
    assert result.prefix == "test-"
    assert result.default_host_dir == "/tmp/test"
    assert AgentTypeName("claude") in result.agent_types
    assert ProviderInstanceName("local") in result.providers
    assert PluginName("my-plugin") in result.plugins
    assert "create" in result.commands
    assert result.logging is not None


def test_parse_config_handles_minimal_config() -> None:
    """_parse_config should handle minimal config with missing optional fields."""
    raw = {"prefix": "test-"}
    result = _parse_config(raw)
    assert result.prefix == "test-"
    assert result.agent_types == {}
    assert result.providers == {}
    assert result.plugins == {}
    assert result.commands == {}
    assert result.logging is None


def test_parse_config_handles_empty_config() -> None:
    """_parse_config should handle empty config dict."""
    result = _parse_config({})
    assert result.prefix is None
    assert result.default_host_dir is None
    assert result.agent_types == {}
    assert result.providers == {}
    assert result.plugins == {}
    assert result.commands == {}
    assert result.logging is None


# =============================================================================
# Tests for on_load_config hook
# =============================================================================


def test_on_load_config_hook_is_called(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Test that the on_load_config hook is called during load_config."""
    # Track whether hook was called
    hook_called = False
    received_config_dict: dict[str, Any] = {}

    class TestPlugin:
        @hookimpl
        def on_load_config(self, config_dict: dict[str, Any]) -> None:
            nonlocal hook_called, received_config_dict
            hook_called = True
            received_config_dict = dict(config_dict)

    # Set up plugin manager with our test plugin
    pm = pluggy.PluginManager("mngr")
    pm.add_hookspecs(hookspecs)
    pm.register(TestPlugin())
    load_all_registries(pm)

    # Ensure no config files interfere
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("MNGR_PREFIX", raising=False)
    monkeypatch.delenv("MNGR_HOST_DIR", raising=False)
    monkeypatch.delenv("MNGR_ROOT_NAME", raising=False)

    # Call load_config
    load_config(pm=pm, context_dir=tmp_path)

    # Verify hook was called
    assert hook_called, "on_load_config hook was not called"
    assert "prefix" in received_config_dict or "providers" in received_config_dict


def test_on_load_config_hook_can_modify_config(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Test that on_load_config hook can modify the config dict."""

    class TestPlugin:
        @hookimpl
        def on_load_config(self, config_dict: dict[str, Any]) -> None:
            # Modify the config dict to change the prefix
            config_dict["prefix"] = "modified-by-plugin-"

    # Set up plugin manager with our test plugin
    pm = pluggy.PluginManager("mngr")
    pm.add_hookspecs(hookspecs)
    pm.register(TestPlugin())
    load_all_registries(pm)

    # Ensure no config files interfere
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("MNGR_PREFIX", raising=False)
    monkeypatch.delenv("MNGR_HOST_DIR", raising=False)
    monkeypatch.delenv("MNGR_ROOT_NAME", raising=False)

    # Call load_config
    mngr_ctx = load_config(pm=pm, context_dir=tmp_path)

    # Verify the config was modified
    assert mngr_ctx.config.prefix == "modified-by-plugin-"


def test_on_load_config_hook_can_add_new_fields(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Test that on_load_config hook can add new config fields."""

    class TestPlugin:
        @hookimpl
        def on_load_config(self, config_dict: dict[str, Any]) -> None:
            # Add a custom agent type
            if "agent_types" not in config_dict:
                config_dict["agent_types"] = {}
            config_dict["agent_types"][AgentTypeName("custom-agent")] = {"cli_args": "--custom"}

    # Set up plugin manager with our test plugin
    pm = pluggy.PluginManager("mngr")
    pm.add_hookspecs(hookspecs)
    pm.register(TestPlugin())
    load_all_registries(pm)

    # Ensure no config files interfere
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("MNGR_PREFIX", raising=False)
    monkeypatch.delenv("MNGR_HOST_DIR", raising=False)
    monkeypatch.delenv("MNGR_ROOT_NAME", raising=False)

    # Call load_config
    mngr_ctx = load_config(pm=pm, context_dir=tmp_path)

    # Verify the agent type was added
    assert AgentTypeName("custom-agent") in mngr_ctx.config.agent_types
    assert mngr_ctx.config.agent_types[AgentTypeName("custom-agent")].cli_args == "--custom"


# =============================================================================
# Tests for get_or_create_profile_dir
# =============================================================================


def testget_or_create_profile_dir_creates_new_profile_when_no_config(tmp_path: Path) -> None:
    """get_or_create_profile_dir should create a new profile when config.toml doesn't exist."""
    base_dir = tmp_path / "mngr"

    result = get_or_create_profile_dir(base_dir)

    # Should have created the directories
    assert (base_dir / "profiles").exists()
    assert result.parent == base_dir / "profiles"
    assert result.exists()

    # Should have written config.toml with the profile ID
    config_path = base_dir / "config.toml"
    assert config_path.exists()
    content = config_path.read_text()
    profile_id = result.name
    assert f'profile = "{profile_id}"' in content


def testget_or_create_profile_dir_reads_existing_profile_from_config(tmp_path: Path) -> None:
    """get_or_create_profile_dir should read existing profile from config.toml."""
    base_dir = tmp_path / "mngr"
    base_dir.mkdir(parents=True, exist_ok=True)
    profiles_dir = base_dir / "profiles"
    profiles_dir.mkdir(exist_ok=True)

    # Create existing profile
    existing_profile_id = "existing123"
    existing_profile_dir = profiles_dir / existing_profile_id
    existing_profile_dir.mkdir(exist_ok=True)

    # Write config.toml pointing to existing profile
    config_path = base_dir / "config.toml"
    config_path.write_text(f'profile = "{existing_profile_id}"\n')

    result = get_or_create_profile_dir(base_dir)

    assert result == existing_profile_dir
    assert result.name == existing_profile_id


def testget_or_create_profile_dir_creates_profile_dir_if_specified_but_missing(tmp_path: Path) -> None:
    """get_or_create_profile_dir should create profile dir if config.toml specifies it but dir doesn't exist."""
    base_dir = tmp_path / "mngr"
    base_dir.mkdir(parents=True, exist_ok=True)
    profiles_dir = base_dir / "profiles"
    profiles_dir.mkdir(exist_ok=True)

    # Write config.toml pointing to non-existent profile
    specified_profile_id = "specified456"
    config_path = base_dir / "config.toml"
    config_path.write_text(f'profile = "{specified_profile_id}"\n')

    result = get_or_create_profile_dir(base_dir)

    # Should have created the specified profile directory
    assert result == profiles_dir / specified_profile_id
    assert result.exists()


def testget_or_create_profile_dir_handles_invalid_config_toml(tmp_path: Path) -> None:
    """get_or_create_profile_dir should handle invalid config.toml by creating new profile."""
    base_dir = tmp_path / "mngr"
    base_dir.mkdir(parents=True, exist_ok=True)

    # Write invalid TOML
    config_path = base_dir / "config.toml"
    config_path.write_text("[invalid toml syntax")

    result = get_or_create_profile_dir(base_dir)

    # Should have created a new profile (with new config)
    assert result.exists()
    assert result.parent == base_dir / "profiles"

    # config.toml should have been overwritten with valid content
    new_content = config_path.read_text()
    assert 'profile = "' in new_content


def testget_or_create_profile_dir_handles_config_without_profile_key(tmp_path: Path) -> None:
    """get_or_create_profile_dir should create new profile if config.toml has no 'profile' key."""
    base_dir = tmp_path / "mngr"
    base_dir.mkdir(parents=True, exist_ok=True)

    # Write valid TOML but without profile key
    config_path = base_dir / "config.toml"
    config_path.write_text('other_key = "value"\n')

    result = get_or_create_profile_dir(base_dir)

    # Should have created a new profile
    assert result.exists()
    assert result.parent == base_dir / "profiles"


def testget_or_create_profile_dir_returns_same_profile_on_subsequent_calls(tmp_path: Path) -> None:
    """get_or_create_profile_dir should return the same profile on subsequent calls."""
    base_dir = tmp_path / "mngr"

    result1 = get_or_create_profile_dir(base_dir)
    result2 = get_or_create_profile_dir(base_dir)

    assert result1 == result2


# =============================================================================
# Tests for _get_or_create_user_id
# =============================================================================


def test_get_or_create_user_id_creates_new_id_when_file_missing(tmp_path: Path) -> None:
    """_get_or_create_user_id should create a new user ID when file doesn't exist."""
    profile_dir = tmp_path / "profile"
    profile_dir.mkdir(parents=True, exist_ok=True)

    result = get_or_create_user_id(profile_dir)

    # Should return a non-empty string (hex UUID, which is 32 chars)
    assert result
    assert len(result) == 32

    # Should have written the ID to file
    user_id_file = profile_dir / "user_id"
    assert user_id_file.exists()
    assert user_id_file.read_text() == result


def test_get_or_create_user_id_reads_existing_id(tmp_path: Path) -> None:
    """_get_or_create_user_id should read existing user ID from file."""
    profile_dir = tmp_path / "profile"
    profile_dir.mkdir(parents=True, exist_ok=True)

    # Create existing user_id file
    existing_id = "abcdef1234567890abcdef1234567890"
    user_id_file = profile_dir / "user_id"
    user_id_file.write_text(existing_id)

    result = get_or_create_user_id(profile_dir)

    assert result == existing_id


def test_get_or_create_user_id_strips_whitespace(tmp_path: Path) -> None:
    """_get_or_create_user_id should strip whitespace from existing ID."""
    profile_dir = tmp_path / "profile"
    profile_dir.mkdir(parents=True, exist_ok=True)

    # Create existing user_id file with whitespace
    existing_id = "abcdef1234567890abcdef1234567890"
    user_id_file = profile_dir / "user_id"
    user_id_file.write_text(f"  {existing_id}  \n")

    result = get_or_create_user_id(profile_dir)

    assert result == existing_id


def test_get_or_create_user_id_returns_same_id_on_subsequent_calls(tmp_path: Path) -> None:
    """_get_or_create_user_id should return the same ID on subsequent calls."""
    profile_dir = tmp_path / "profile"
    profile_dir.mkdir(parents=True, exist_ok=True)

    result1 = get_or_create_user_id(profile_dir)
    result2 = get_or_create_user_id(profile_dir)

    assert result1 == result2
