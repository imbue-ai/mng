import os
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from typing import Sequence
from uuid import uuid4

import pluggy

from imbue.concurrency_group.concurrency_group import ConcurrencyGroup
from imbue.imbue_common.model_update import to_update
from imbue.mngr.agents.agent_registry import get_agent_config_class
from imbue.mngr.config.data_types import AgentTypeConfig
from imbue.mngr.config.data_types import CommandDefaults
from imbue.mngr.config.data_types import CreateTemplate
from imbue.mngr.config.data_types import CreateTemplateName
from imbue.mngr.config.data_types import LoggingConfig
from imbue.mngr.config.data_types import MngrConfig
from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.config.data_types import PROFILES_DIRNAME
from imbue.mngr.config.data_types import PluginConfig
from imbue.mngr.config.data_types import ProviderInstanceConfig
from imbue.mngr.config.data_types import ROOT_CONFIG_FILENAME
from imbue.mngr.config.plugin_registry import get_plugin_config_class
from imbue.mngr.errors import ConfigNotFoundError
from imbue.mngr.errors import ConfigParseError
from imbue.mngr.errors import UnknownBackendError
from imbue.mngr.primitives import AgentTypeName
from imbue.mngr.primitives import PluginName
from imbue.mngr.primitives import ProviderInstanceName
from imbue.mngr.providers.registry import get_config_class as get_provider_config_class
from imbue.mngr.utils.git_utils import find_git_worktree_root

# Environment variable prefix for command config overrides.
# Format: MNGR_COMMANDS_<COMMANDNAME>_<VARNAME>=<value>
# Example: MNGR_COMMANDS_CREATE_NEW_BRANCH_PREFIX=agent/
#
# IMPORTANT: Command names MUST be single words (no spaces, hyphens, or underscores).
# This is because we use the first underscore after "MNGR_COMMANDS_" to separate
# the command name from the parameter name. If command names contained underscores,
# parsing would be ambiguous. For example, "MNGR_COMMANDS_FOO_BAR_BAZ" could be:
#   - command="foo", param="bar_baz"
#   - command="foo_bar", param="baz"
#
# Any future plugins that register custom commands must follow this single-word rule.
_ENV_COMMANDS_PREFIX = "MNGR_COMMANDS_"


# FIXME: sadly, putting in random keys into the various config locations often silently fails. We should *at least* warn when there are unknown keys.
#  The behavior of whether to warn/error/ignore should be configurable as well! (both via an env var and via config file)
#  I made a quick example of how to do this correctly in _parse_config (but the other sub parsers need to be updated as well)
def load_config(
    pm: pluggy.PluginManager,
    context_dir: Path | None = None,
    enabled_plugins: Sequence[str] | None = None,
    disabled_plugins: Sequence[str] | None = None,
    is_interactive: bool = False,
    concurrency_group: ConcurrencyGroup | None = None,
) -> MngrContext:
    """Load and merge configuration from all sources.

    Precedence (lowest to highest):
    1. User config (~/.{root_name}/profiles/<profile_id>/settings.toml)
    2. Project config (.{root_name}/settings.toml at context_dir or git root)
    3. Local config (.{root_name}/settings.local.toml at context_dir or git root)
    4. Environment variables (MNGR_ROOT_NAME, MNGR_PREFIX, MNGR_HOST_DIR)
    5. CLI arguments (handled by caller)

    MNGR_ROOT_NAME is used to derive:
    1. Config file paths (where to look for settings files)
    2. Defaults for prefix and default_host_dir (if not set in config files)

    Explicit MNGR_PREFIX/MNGR_HOST_DIR values override MNGR_ROOT_NAME-derived defaults.

    Returns MngrContext containing both the final MngrConfig and a reference to the plugin manager.
    """

    # Read MNGR_ROOT_NAME early to use for config file discovery
    root_name = os.environ.get("MNGR_ROOT_NAME", "mngr")

    # Determine base directory (may be overridden by env var)
    env_host_dir = os.environ.get("MNGR_HOST_DIR")
    base_dir = Path(env_host_dir) if env_host_dir else Path(f"~/.{root_name}")
    base_dir = base_dir.expanduser()

    # Get/create profile directory first (needed for user config
    profile_dir = get_or_create_profile_dir(base_dir)

    # Start with base config that has defaults based on root_name
    # Use model_construct with None to allow merging to work properly
    config = MngrConfig.model_construct(
        prefix=f"{root_name}-",
        default_host_dir=Path(f"~/.{root_name}"),
        agent_types={},
        providers={},
        plugins={},
        logging=LoggingConfig(),
        commands={"create": CommandDefaults(defaults={"pass_host_env": ["EDITOR"]})},
    )

    # Load user config from profile directory
    user_config_path = _get_user_config_path(profile_dir)
    if user_config_path.exists():
        try:
            raw_user = _load_toml(user_config_path)
            user_config = _parse_config(raw_user)
            config = config.merge_with(user_config)
        except ConfigNotFoundError:
            pass

    # Load project config from context_dir or auto-discover
    project_config_path = _find_project_config(context_dir, root_name, concurrency_group)
    if project_config_path is not None and project_config_path.exists():
        raw_project = _load_toml(project_config_path)
        project_config = _parse_config(raw_project)
        config = config.merge_with(project_config)

    # Load local config from context_dir or auto-discover
    local_config_path = _find_local_config(context_dir, root_name, concurrency_group)
    if local_config_path is not None and local_config_path.exists():
        raw_local = _load_toml(local_config_path)
        local_config = _parse_config(raw_local)
        config = config.merge_with(local_config)

    # Apply environment variable overrides
    prefix = os.environ.get("MNGR_PREFIX")
    default_host_dir = os.environ.get("MNGR_HOST_DIR")

    # Build a dict with non-None values for final validation
    config_dict: dict[str, Any] = {}

    # Apply env var overrides, or use merged values
    if prefix is not None:
        config_dict["prefix"] = prefix
    elif config.prefix is not None:
        config_dict["prefix"] = config.prefix
    else:
        # Neither env var nor config has prefix - will use pydantic default
        pass

    if default_host_dir is not None:
        config_dict["default_host_dir"] = Path(default_host_dir)
    elif config.default_host_dir is not None:
        config_dict["default_host_dir"] = config.default_host_dir
    else:
        # Neither env var nor config has default_host_dir - will use pydantic default
        pass

    # Always include agent_types, providers, plugins, commands, and create_templates (they default to empty dicts)
    config_dict["agent_types"] = config.agent_types
    config_dict["providers"] = config.providers
    config_dict["plugins"] = config.plugins
    config_dict["commands"] = config.commands
    config_dict["create_templates"] = config.create_templates

    # Apply environment variable overrides for commands
    # Format: MNGR_COMMANDS_<COMMANDNAME>_<PARAMNAME>=<value>
    # See _ENV_COMMANDS_PREFIX comment for details on the single-word command name requirement
    env_command_overrides = _parse_command_env_vars(os.environ)
    if env_command_overrides:
        config_dict["commands"] = _merge_command_defaults(
            config_dict["commands"],
            env_command_overrides,
        )

    # Apply CLI plugin overrides
    config_dict["plugins"], config_dict["disabled_plugins"] = _apply_plugin_overrides(
        config_dict["plugins"],
        enabled_plugins,
        disabled_plugins,
    )

    # Include logging if not None
    if config.logging is not None:
        config_dict["logging"] = config.logging

    config_dict["is_allowed_in_pytest"] = config.is_allowed_in_pytest
    config_dict["pre_command_scripts"] = config.pre_command_scripts

    # Allow plugins to modify config_dict before validation
    pm.hook.on_load_config(config_dict=config_dict)

    # Validate and apply defaults using normal constructor
    final_config = MngrConfig.model_validate(config_dict)

    # check whether we're in pytest
    if not final_config.is_allowed_in_pytest:
        if "PYTEST_CURRENT_TEST" in os.environ:
            raise ConfigParseError(
                "Running mngr within pytest is not allowed by the current configuration. This can happen when tests are poorly written, and load the .mngr/settings.toml file from the root of the mngr project"
            )

    # Return MngrContext containing both config and plugin manager
    mngr_ctx_kwargs: dict[str, Any] = {
        "config": final_config,
        "pm": pm,
        "is_interactive": is_interactive,
        "profile_dir": profile_dir,
    }
    if concurrency_group is not None:
        mngr_ctx_kwargs["concurrency_group"] = concurrency_group
    return MngrContext(**mngr_ctx_kwargs)


def get_or_create_profile_dir(base_dir: Path) -> Path:
    """Get or create the profile directory for this mngr installation.

    The profile directory is stored at ~/.mngr/profiles/<profile_id>/. The active
    profile is specified in ~/.mngr/config.toml. If no profile exists, a new one
    is created with a generated profile ID and saved to config.toml.
    """
    base_dir.mkdir(parents=True, exist_ok=True)
    profiles_dir = base_dir / PROFILES_DIRNAME
    profiles_dir.mkdir(parents=True, exist_ok=True)
    config_path = base_dir / ROOT_CONFIG_FILENAME

    # Try to read the active profile from config.toml
    if config_path.exists():
        try:
            with open(config_path, "rb") as f:
                root_config = tomllib.load(f)
            profile_id = root_config.get("profile")
            if profile_id:
                profile_dir = profiles_dir / profile_id
                if profile_dir.exists() and profile_dir.is_dir():
                    return profile_dir
                # Profile specified but doesn't exist - create it
                profile_dir.mkdir(parents=True, exist_ok=True)
                return profile_dir
        except tomllib.TOMLDecodeError:
            # Invalid config.toml - will create new profile
            pass

    # No valid config.toml or no profile specified - create a new profile
    profile_id = uuid4().hex
    profile_dir = profiles_dir / profile_id
    profile_dir.mkdir(parents=True, exist_ok=True)

    # Save the new profile ID to config.toml
    config_path.write_text(f'profile = "{profile_id}"\n')

    return profile_dir


# =============================================================================
# Config File Discovery
# =============================================================================


def _get_user_config_path(profile_dir: Path) -> Path:
    """Get the user config path based on profile directory."""
    return profile_dir / "settings.toml"


def _get_project_config_name(root_name: str) -> Path:
    """Get the project config relative path based on root name."""
    return Path(f".{root_name}") / "settings.toml"


def _get_local_config_name(root_name: str) -> Path:
    """Get the local config relative path based on root name."""
    return Path(f".{root_name}") / "settings.local.toml"


def _find_project_root(start: Path | None = None, cg: ConcurrencyGroup | None = None) -> Path | None:
    """Find the project root by looking for git worktree root."""
    if cg is None:
        # Fallback for when CG is not available (e.g., test contexts).
        # Create a short-lived CG just for this operation.
        with ConcurrencyGroup(name="config-loader-project-root") as fallback_cg:
            return find_git_worktree_root(start, fallback_cg)
    return find_git_worktree_root(start, cg)


def _find_project_config(context_dir: Path | None, root_name: str, cg: ConcurrencyGroup | None) -> Path | None:
    """Find the project config file."""
    root = context_dir or _find_project_root(cg=cg)
    if root is None:
        return None
    config_path = root / _get_project_config_name(root_name)
    return config_path if config_path.exists() else None


def _find_local_config(context_dir: Path | None, root_name: str, cg: ConcurrencyGroup | None) -> Path | None:
    """Find the local config file."""
    root = context_dir or _find_project_root(cg=cg)
    if root is None:
        return None
    config_path = root / _get_local_config_name(root_name)
    return config_path if config_path.exists() else None


# =============================================================================
# Config Loading
# =============================================================================


def _load_toml(path: Path) -> dict[str, Any]:
    """Load and parse a TOML file."""
    if not path.exists():
        raise ConfigNotFoundError(f"Config file not found: {path}")

    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ConfigParseError(f"Failed to parse {path}: {e}") from e


def _parse_providers(
    raw_providers: dict[str, dict[str, Any]],
) -> dict[ProviderInstanceName, ProviderInstanceConfig]:
    """Parse provider configs using the registry.

    Uses model_construct to bypass validation and explicitly set None for unset fields.
    """
    providers: dict[ProviderInstanceName, ProviderInstanceConfig] = {}

    for name, raw_config in raw_providers.items():
        backend = raw_config.get("backend") or name
        try:
            config_class = get_provider_config_class(backend)
        except UnknownBackendError as e:
            raise ConfigParseError(f"Provider '{name}' missing required 'backend' field") from e
        providers[ProviderInstanceName(name)] = config_class.model_construct(**raw_config)

    return providers


def _parse_agent_types(
    raw_types: dict[str, dict[str, Any]],
) -> dict[AgentTypeName, AgentTypeConfig]:
    """Parse agent type configs using the registry.

    Uses model_construct to bypass validation and explicitly set None for unset fields.
    """
    agent_types: dict[AgentTypeName, AgentTypeConfig] = {}

    for name, raw_config in raw_types.items():
        config_class = get_agent_config_class(name)
        agent_types[AgentTypeName(name)] = config_class.model_construct(**raw_config)

    return agent_types


def _parse_plugins(
    raw_plugins: dict[str, dict[str, Any]],
) -> dict[PluginName, PluginConfig]:
    """Parse plugin configs using the registry.

    Uses model_construct to bypass validation and explicitly set None for unset fields.
    """
    plugins: dict[PluginName, PluginConfig] = {}

    for name, raw_config in raw_plugins.items():
        config_class = get_plugin_config_class(name)
        plugins[PluginName(name)] = config_class.model_construct(**raw_config)

    return plugins


def _apply_plugin_overrides(
    plugins: dict[PluginName, PluginConfig],
    enabled_plugins: Sequence[str] | None,
    disabled_plugins: Sequence[str] | None,
) -> tuple[dict[PluginName, PluginConfig], frozenset[str]]:
    """Apply CLI plugin enable/disable overrides and filter out disabled plugins.

    Returns a tuple of (enabled_plugins_dict, disabled_plugin_names).
    """
    # Create a mutable copy
    result: dict[PluginName, PluginConfig] = dict(plugins)

    # Apply enabled plugins (add if not present, or set enabled=True)
    if enabled_plugins:
        for plugin_name_str in enabled_plugins:
            plugin_name = PluginName(plugin_name_str)
            if plugin_name in result:
                # Plugin exists - set enabled=True
                existing = result[plugin_name]
                result[plugin_name] = existing.model_copy_update(
                    to_update(existing.field_ref().enabled, True),
                )
            else:
                # Plugin doesn't exist - create with enabled=True
                config_class = get_plugin_config_class(plugin_name_str)
                result[plugin_name] = config_class(enabled=True)

    # Apply disabled plugins (set enabled=False)
    if disabled_plugins:
        for plugin_name_str in disabled_plugins:
            plugin_name = PluginName(plugin_name_str)
            if plugin_name in result:
                # Plugin exists - set enabled=False
                existing = result[plugin_name]
                result[plugin_name] = existing.model_copy_update(
                    to_update(existing.field_ref().enabled, False),
                )
            else:
                # Plugin doesn't exist - create with enabled=False
                config_class = get_plugin_config_class(plugin_name_str)
                result[plugin_name] = config_class(enabled=False)

    # Collect disabled plugin names and filter out disabled plugins
    disabled_names = frozenset(str(name) for name, config in result.items() if not config.enabled)
    enabled_result = {name: config for name, config in result.items() if config.enabled}
    return enabled_result, disabled_names


def _parse_logging_config(raw_logging: dict[str, Any]) -> LoggingConfig:
    """Parse logging config.

    Uses model_construct to bypass validation and explicitly set None for unset fields.
    """
    return LoggingConfig.model_construct(**raw_logging)


def _parse_commands(raw_commands: dict[str, dict[str, Any]]) -> dict[str, CommandDefaults]:
    """Parse command defaults from config.

    Format: commands.{command_name}.{param_name} = value
    Example: [commands.create]
             new_host = "docker"
             connect = false

    Uses model_construct to bypass validation and explicitly set None for unset fields.
    """
    commands: dict[str, CommandDefaults] = {}

    for command_name, raw_defaults in raw_commands.items():
        commands[command_name] = CommandDefaults.model_construct(defaults=raw_defaults)

    return commands


def _parse_create_templates(raw_templates: dict[str, dict[str, Any]]) -> dict[CreateTemplateName, CreateTemplate]:
    """Parse create templates from config.

    Format: create_templates.{template_name}.{param_name} = value
    Example: [create_templates.modal-dev]
             new_host = "modal"
             target_path = "/root/workspace"

    Uses model_construct to bypass validation and explicitly set None for unset fields.
    """
    templates: dict[CreateTemplateName, CreateTemplate] = {}

    for template_name, raw_options in raw_templates.items():
        templates[CreateTemplateName(template_name)] = CreateTemplate.model_construct(options=raw_options)

    return templates


def _parse_config(raw: dict[str, Any]) -> MngrConfig:
    """Parse a raw config dict into MngrConfig.

    Uses model_construct to bypass defaults and explicitly set None for unset fields.
    """
    # Build kwargs with None for unset scalar fields
    kwargs: dict[str, Any] = {}
    kwargs["prefix"] = raw.pop("prefix", None)
    kwargs["default_host_dir"] = raw.pop("default_host_dir", None)
    kwargs["agent_types"] = _parse_agent_types(raw.pop("agent_types", {})) if "agent_types" in raw else {}
    kwargs["providers"] = _parse_providers(raw.pop("providers", {})) if "providers" in raw else {}
    kwargs["plugins"] = _parse_plugins(raw.pop("plugins", {})) if "plugins" in raw else {}
    kwargs["commands"] = _parse_commands(raw.pop("commands", {})) if "commands" in raw else {}
    kwargs["create_templates"] = (
        _parse_create_templates(raw.pop("create_templates", {})) if "create_templates" in raw else {}
    )
    kwargs["logging"] = _parse_logging_config(raw.pop("logging", {})) if "logging" in raw else None
    kwargs["is_allowed_in_pytest"] = raw.pop("is_allowed_in_pytest", {}) if "is_allowed_in_pytest" in raw else None
    kwargs["pre_command_scripts"] = raw.pop("pre_command_scripts", {}) if "pre_command_scripts" in raw else None

    if len(raw) > 0:
        raise ConfigParseError(f"Unknown configuration fields: {list(raw.keys())}")

    # Use model_construct to bypass field defaults
    return MngrConfig.model_construct(**kwargs)


# =============================================================================
# Environment Variable Overrides for Commands
# =============================================================================


def _parse_command_env_vars(environ: Mapping[str, str]) -> dict[str, CommandDefaults]:
    """Parse environment variables to extract command config overrides.

    Looks for environment variables matching the pattern:
        MNGR_COMMANDS_<COMMANDNAME>_<PARAMNAME>=<value>

    where:
        - COMMANDNAME is the command name in uppercase (e.g., CREATE, LIST)
        - PARAMNAME is the parameter name in uppercase with underscores (e.g., NEW_BRANCH_PREFIX)
        - value is the string value to set

    The command name is determined by the first underscore after "MNGR_COMMANDS_".
    The remaining part becomes the parameter name (lowercased).

    IMPORTANT: Command names MUST be single words (no underscores) for unambiguous parsing.
    See the comment at _ENV_COMMANDS_PREFIX for details.

    Examples:
        MNGR_COMMANDS_CREATE_NEW_BRANCH_PREFIX=agent/
            -> commands["create"]["new_branch_prefix"] = "agent/"

        MNGR_COMMANDS_CREATE_CONNECT=false
            -> commands["create"]["connect"] = "false"

        MNGR_COMMANDS_LIST_FORMAT=json
            -> commands["list"]["format"] = "json"

    Returns:
        Dict mapping command names to CommandDefaults with the parsed values.
    """
    commands: dict[str, dict[str, Any]] = {}

    for env_key, env_value in environ.items():
        if not env_key.startswith(_ENV_COMMANDS_PREFIX):
            continue

        # Strip the prefix to get "<COMMANDNAME>_<PARAMNAME>"
        suffix = env_key[len(_ENV_COMMANDS_PREFIX) :]
        if not suffix:
            continue

        # Find the first underscore to split command name from param name
        underscore_idx = suffix.find("_")
        if underscore_idx == -1:
            # No underscore means no param name, skip this
            continue

        command_name = suffix[:underscore_idx].lower()
        param_name = suffix[underscore_idx + 1 :].lower()

        if not command_name or not param_name:
            continue

        # Initialize the command's dict if needed
        if command_name not in commands:
            commands[command_name] = {}

        # Store as string - type conversion happens downstream in click/pydantic
        # where the actual type information is available
        commands[command_name][param_name] = env_value

    # Convert raw dicts to CommandDefaults
    result: dict[str, CommandDefaults] = {}
    for command_name, params in commands.items():
        result[command_name] = CommandDefaults(defaults=params)

    return result


def _merge_command_defaults(
    base: dict[str, CommandDefaults],
    override: dict[str, CommandDefaults],
) -> dict[str, CommandDefaults]:
    """Merge two command defaults dicts, with override taking precedence."""
    result: dict[str, CommandDefaults] = dict(base)

    for command_name, override_defaults in override.items():
        if command_name in result:
            result[command_name] = result[command_name].merge_with(override_defaults)
        else:
            result[command_name] = override_defaults

    return result
