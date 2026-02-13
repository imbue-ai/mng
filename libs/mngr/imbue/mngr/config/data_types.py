from __future__ import annotations

import os
import shlex
from pathlib import Path
from typing import Any
from typing import Self
from typing import TypeVar
from uuid import uuid4

import pluggy
from pydantic import Field
from pydantic import GetCoreSchemaHandler
from pydantic import field_validator
from pydantic_core import CoreSchema
from pydantic_core import core_schema

from imbue.concurrency_group.concurrency_group import ConcurrencyGroup
from imbue.imbue_common.frozen_model import FrozenModel
from imbue.imbue_common.pure import pure
from imbue.mngr.errors import ConfigParseError
from imbue.mngr.errors import ParseSpecError
from imbue.mngr.primitives import AgentTypeName
from imbue.mngr.primitives import CommandString
from imbue.mngr.primitives import LifecycleHook
from imbue.mngr.primitives import LogLevel
from imbue.mngr.primitives import OutputFormat
from imbue.mngr.primitives import Permission
from imbue.mngr.primitives import PluginName
from imbue.mngr.primitives import ProviderBackendName
from imbue.mngr.primitives import ProviderInstanceName

USER_ID_FILENAME = "user_id"
PROFILES_DIRNAME = "profiles"
ROOT_CONFIG_FILENAME = "config.toml"

# === Helper Functions ===

T = TypeVar("T")


@pure
def merge_cli_args(base: tuple[str, ...], override: tuple[str, ...]) -> tuple[str, ...]:
    """Merge CLI arguments, concatenating if both present."""
    if override:
        return base + override
    return base


@pure
def merge_list_fields(base: list[T], override: list[T] | None) -> list[T]:
    """Merge list fields, concatenating if override is not None."""
    if override is not None:
        return list(base) + list(override)
    return base


K = TypeVar("K")
V = TypeVar("V")


@pure
def merge_dict_fields(base: dict[K, V], override: dict[K, V] | None) -> dict[K, V]:
    """Merge dict fields, with override keys taking precedence."""
    if override is not None:
        return {**base, **override}
    return base


# === Value Types ===


class EnvVar(FrozenModel):
    """Environment variable as KEY=VALUE."""

    key: str = Field(description="The environment variable name")
    value: str = Field(description="The environment variable value")

    @classmethod
    def from_string(cls, s: str) -> "EnvVar":
        """Parse a KEY=VALUE string into an EnvVar."""
        if "=" not in s:
            raise ParseSpecError(f"Environment variable must be in KEY=VALUE format, got: {s}")
        key, value = s.split("=", 1)
        return cls(key=key.strip(), value=value.strip())


class HookDefinition(FrozenModel):
    """Lifecycle hook definition as NAME:COMMAND."""

    hook: LifecycleHook = Field(description="The lifecycle hook name")
    command: str = Field(description="The command to run")

    @classmethod
    def from_string(cls, s: str) -> "HookDefinition":
        """Parse a NAME:COMMAND string into a HookDefinition."""
        if ":" not in s:
            raise ParseSpecError(f"Hook must be in NAME:COMMAND format, got: {s}")
        name, command = s.split(":", 1)
        # Normalize name: convert hyphens to underscores and uppercase
        normalized_name = name.strip().upper().replace("-", "_")
        try:
            hook = LifecycleHook(normalized_name)
        except ValueError:
            valid = ", ".join(h.value.lower().replace("_", "-") for h in LifecycleHook)
            raise ParseSpecError(f"Invalid hook name '{name}'. Valid hooks: {valid}") from None
        return cls(hook=hook, command=command.strip())


# === Config Types ===


class AgentTypeConfig(FrozenModel):
    """Defines a custom agent type that inherits from an existing type."""

    parent_type: AgentTypeName | None = Field(
        default=None,
        description="Base type to inherit from (must be a plugin-provided or command type, not another custom type)",
    )
    command: CommandString | None = Field(
        default=None,
        description="Command to run for this agent type",
    )
    cli_args: tuple[str, ...] = Field(
        default=(),
        description="Additional CLI arguments to pass to the agent",
    )
    permissions: list[Permission] = Field(
        default_factory=list,
        description="Explicit list of permissions (overrides parent type permissions)",
    )

    @field_validator("cli_args", mode="before")
    @classmethod
    def _normalize_cli_args(cls, value: str | list[str] | tuple[str, ...]) -> tuple[str, ...]:
        if isinstance(value, str):
            return tuple(shlex.split(value)) if value else ()
        return tuple(value)

    def merge_with(self, override: Self) -> Self:
        """Merge this config with an override config.

        Scalar fields: override wins if not None
        Lists: concatenate both lists
        """
        # Ensure override is same type or subclass of self's type
        if not isinstance(override, self.__class__):
            raise ConfigParseError(f"Cannot merge {self.__class__.__name__} with different agent config type")

        # Merge parent_type (scalar - override wins if not None)
        merged_parent_type = override.parent_type if override.parent_type is not None else self.parent_type

        # Merge command (scalar - override wins if not None)
        merged_command = override.command if override.command is not None else self.command

        # Merge cli_args (concatenate both tuples)
        merged_cli_args = merge_cli_args(self.cli_args, override.cli_args)

        # Merge permissions (list - concatenate if override is not None)
        merged_permissions = merge_list_fields(self.permissions, override.permissions)

        return self.__class__(
            parent_type=merged_parent_type,
            command=merged_command,
            cli_args=merged_cli_args,
            permissions=merged_permissions,
        )


class ProviderInstanceConfig(FrozenModel):
    """Defines a custom provider instance."""

    backend: ProviderBackendName = Field(
        description="Provider backend to use (e.g., 'docker', 'modal', 'aws')",
    )
    is_enabled: bool | None = Field(
        default=None,
        description="Whether this provider instance is enabled. Set to false to disable without removing configuration.",
    )

    def merge_with(self, override: "ProviderInstanceConfig") -> "ProviderInstanceConfig":
        """Merge this config with an override config.

        Scalar fields: override wins if not None
        List fields: concatenate both lists
        Dict fields: merge keys, with override keys taking precedence
        """
        # Ensure override is same type as self
        if not isinstance(override, self.__class__):
            raise ConfigParseError(f"Cannot merge {self.__class__.__name__} with different provider config type")

        # Merge all fields: for each field, use appropriate merge strategy based on type
        # Backend always comes from override
        merged_values: dict[str, Any] = {}
        for field_name in self.__class__.model_fields:
            if field_name == "backend":
                merged_values[field_name] = override.backend
            else:
                base_value = getattr(self, field_name)
                override_value = getattr(override, field_name)
                if isinstance(base_value, list):
                    # Lists: concatenate
                    merged_values[field_name] = merge_list_fields(base_value, override_value)
                elif isinstance(base_value, dict):
                    # Dicts: merge keys with override taking precedence
                    merged_values[field_name] = merge_dict_fields(base_value, override_value)
                elif override_value is not None:
                    # Scalars: override wins if not None
                    merged_values[field_name] = override_value
                else:
                    merged_values[field_name] = base_value
        return self.__class__(**merged_values)


class PluginConfig(FrozenModel):
    """Base configuration for a plugin."""

    enabled: bool = Field(
        default=True,
        description="Whether this plugin is enabled",
    )

    def merge_with(self, override: "PluginConfig") -> "PluginConfig":
        """Merge this config with an override config.

        Scalar fields: override wins if not None
        """
        merged_enabled = override.enabled if override.enabled is not None else self.enabled
        return self.__class__(enabled=merged_enabled)


class LoggingConfig(FrozenModel):
    """Logging configuration for mngr."""

    file_level: LogLevel = Field(
        default=LogLevel.DEBUG,
        description="Log level for file logging",
    )
    log_dir: Path = Field(
        default=Path("logs"),
        description="Directory for log files (relative to data root if relative)",
    )
    max_log_files: int = Field(
        default=1000,
        description="Maximum number of log files to keep",
    )
    max_log_size_mb: int = Field(
        default=10,
        description="Maximum size of each log file in MB",
    )
    console_level: LogLevel = Field(
        default=LogLevel.BUILD,
        description="Log level for console output",
    )
    is_logging_commands: bool = Field(
        default=True,
        description="Log what commands were executed",
    )
    is_logging_command_output: bool = Field(
        default=False,
        description="Log stdout/stderr from executed commands",
    )
    is_logging_env_vars: bool = Field(
        default=False,
        description="Log environment variables (security risk)",
    )

    def merge_with(self, override: "LoggingConfig") -> "LoggingConfig":
        """Merge this config with an override config.

        Scalar fields: override wins if not None
        """
        return LoggingConfig(
            file_level=override.file_level if override.file_level is not None else self.file_level,
            log_dir=override.log_dir if override.log_dir is not None else self.log_dir,
            max_log_files=override.max_log_files if override.max_log_files is not None else self.max_log_files,
            max_log_size_mb=override.max_log_size_mb if override.max_log_size_mb is not None else self.max_log_size_mb,
            console_level=override.console_level if override.console_level is not None else self.console_level,
            is_logging_commands=override.is_logging_commands
            if override.is_logging_commands is not None
            else self.is_logging_commands,
            is_logging_command_output=override.is_logging_command_output
            if override.is_logging_command_output is not None
            else self.is_logging_command_output,
            is_logging_env_vars=override.is_logging_env_vars
            if override.is_logging_env_vars is not None
            else self.is_logging_env_vars,
        )


class CommandDefaults(FrozenModel):
    """Default values for CLI command parameters.

    This allows config files to override default values for CLI arguments.
    Only parameters that were not explicitly set by the user will use these defaults.
    Field names should match the CLI parameter names (after click's conversion).
    """

    # Store as a flexible dict since we don't know all possible CLI parameters ahead of time
    defaults: dict[str, Any] = Field(
        default_factory=dict,
        description="Map of parameter name to default value",
    )

    def merge_with(self, override: Self) -> Self:
        """Merge this config with an override config.

        For command defaults, later configs completely override earlier ones.
        """
        merged_defaults = {**self.defaults, **override.defaults}
        return self.__class__(defaults=merged_defaults)


class CreateTemplateName(str):
    """Name of a create template."""

    def __new__(cls, value: str) -> Self:
        if not value:
            raise ParseSpecError("Template name cannot be empty")
        return super().__new__(cls, value)

    @classmethod
    def __get_pydantic_core_schema__(
        cls,
        source_type: Any,
        handler: GetCoreSchemaHandler,
    ) -> CoreSchema:
        return core_schema.no_info_after_validator_function(
            cls,
            core_schema.str_schema(min_length=1),
            serialization=core_schema.to_string_ser_schema(),
        )


class CreateTemplate(FrozenModel):
    """Template for the create command.

    Templates are named presets of create command arguments that can be applied
    using --template <name>. All fields are optional; only specified fields
    will override the defaults when the template is applied.

    Templates are useful for setting up common configurations for different
    providers or environments (e.g., different paths in remote containers vs locally).
    """

    # Store as a flexible dict since templates can contain any create command parameter
    options: dict[str, Any] = Field(
        default_factory=dict,
        description="Map of parameter name to value for create command options",
    )

    def merge_with(self, override: Self) -> Self:
        """Merge this template with an override template.

        For templates, later configs override earlier ones on a per-key basis.
        """
        merged_options = {**self.options, **override.options}
        return self.__class__(options=merged_options)


class MngrConfig(FrozenModel):
    """Root configuration model for mngr."""

    prefix: str = Field(
        default="mngr-",
        description="Prefix for naming resources (tmux sessions, containers, etc.)",
    )
    default_host_dir: Path = Field(
        default=Path("~/.mngr"),
        description="Default base directory for mngr data on hosts (can be overridden per provider instance)",
    )
    unset_vars: list[str] = Field(
        # these are necessary to prevent tmux from accidentally sticking test data in history files
        default_factory=lambda: list(("HISTFILE", "PROFILE", "VIRTUAL_ENV")),
        description="Environment variables to unset when creating agent tmux sessions",
    )
    pager: str | None = Field(
        default=None,
        description="Pager command for help output (e.g., 'less'). If None, uses PAGER env var or 'less' as fallback.",
    )
    enabled_backends: list[ProviderBackendName] = Field(
        default_factory=list,
        description="List of enabled provider backends. If empty, all backends are enabled. If non-empty, only the listed backends are enabled.",
    )
    agent_types: dict[AgentTypeName, AgentTypeConfig] = Field(
        default_factory=dict,
        description="Custom agent type definitions",
    )
    providers: dict[ProviderInstanceName, ProviderInstanceConfig] = Field(
        default_factory=dict,
        description="Custom provider instance definitions",
    )
    plugins: dict[PluginName, PluginConfig] = Field(
        default_factory=dict,
        description="Plugin configurations",
    )
    disabled_plugins: frozenset[str] = Field(
        default_factory=frozenset,
        description="Set of plugin names that were explicitly disabled (used to filter backends)",
    )
    commands: dict[str, CommandDefaults] = Field(
        default_factory=dict,
        description="Default values for CLI command parameters (e.g., 'commands.create')",
    )
    create_templates: dict[CreateTemplateName, CreateTemplate] = Field(
        default_factory=dict,
        description="Named templates for the create command (e.g., 'create_templates.modal-dev')",
    )
    pre_command_scripts: dict[str, list[str]] = Field(
        default_factory=dict,
        description="Commands to run before CLI commands execute, keyed by command name (e.g., 'create': ['echo hello', 'validate.sh'])",
    )
    logging: LoggingConfig = Field(
        default_factory=LoggingConfig,
        description="Logging configuration",
    )
    is_remote_agent_installation_allowed: bool = Field(
        default=True,
        description="Whether to allow automatic installation of agents (e.g. Claude) on remote hosts. "
        "When False, raises an error if the agent is not already installed on the remote host.",
    )
    is_allowed_in_pytest: bool = Field(
        default=True,
        description="Set this to False to prevent loading this config in pytest runs",
    )

    def merge_with(self, override: Self) -> Self:
        """Merge this config with an override config.

        Scalar fields: override wins if not None
        Dicts: merge keys, with per-key merge for nested config objects
        Lists: concatenate both lists
        """
        # Merge prefix (scalar - override wins if not None)
        merged_prefix = self.prefix
        if override.prefix is not None:
            merged_prefix = override.prefix

        # Merge default_host_dir (scalar - override wins if not None)
        merged_default_host_dir = self.default_host_dir
        if override.default_host_dir is not None:
            merged_default_host_dir = override.default_host_dir

        # Merge pager (scalar - override wins if not None)
        merged_pager = override.pager if override.pager is not None else self.pager

        # Merge unset_vars (list - concatenate)
        merged_unset_vars = list(self.unset_vars) + list(override.unset_vars)

        # Merge enabled_backends (list - override wins if not empty, otherwise keep base)
        merged_enabled_backends = override.enabled_backends if override.enabled_backends else self.enabled_backends

        # Merge agent_types (dict - merge keys, with per-key merge)
        merged_agent_types: dict[AgentTypeName, AgentTypeConfig] = {}
        all_type_keys = set(self.agent_types.keys()) | set(override.agent_types.keys())
        for key in all_type_keys:
            if key in self.agent_types and key in override.agent_types:
                # Both have this key - merge the configs
                merged_agent_types[key] = self.agent_types[key].merge_with(override.agent_types[key])
            elif key in override.agent_types:
                # Only override has this key
                merged_agent_types[key] = override.agent_types[key]
            else:
                # Only base has this key
                merged_agent_types[key] = self.agent_types[key]

        # Merge providers (dict - merge keys, with per-key merge)
        merged_providers: dict[ProviderInstanceName, ProviderInstanceConfig] = {}
        all_provider_keys = set(self.providers.keys()) | set(override.providers.keys())
        for key in all_provider_keys:
            if key in self.providers and key in override.providers:
                # Both have this key - merge the configs
                merged_providers[key] = self.providers[key].merge_with(override.providers[key])
            elif key in override.providers:
                # Only override has this key
                merged_providers[key] = override.providers[key]
            else:
                # Only base has this key
                merged_providers[key] = self.providers[key]

        # Merge plugins (dict - merge keys, with per-key merge)
        merged_plugins: dict[PluginName, PluginConfig] = {}
        all_plugin_keys = set(self.plugins.keys()) | set(override.plugins.keys())
        for key in all_plugin_keys:
            if key in self.plugins and key in override.plugins:
                # Both have this key - merge the configs
                merged_plugins[key] = self.plugins[key].merge_with(override.plugins[key])
            elif key in override.plugins:
                # Only override has this key
                merged_plugins[key] = override.plugins[key]
            else:
                # Only base has this key
                merged_plugins[key] = self.plugins[key]

        # Merge disabled_plugins (union of both sets)
        merged_disabled_plugins = self.disabled_plugins | override.disabled_plugins

        # Merge commands (dict - merge keys, with per-key merge)
        merged_commands: dict[str, CommandDefaults] = {}
        all_command_keys = set(self.commands.keys()) | set(override.commands.keys())
        for key in all_command_keys:
            if key in self.commands and key in override.commands:
                # Both have this key - merge the configs
                merged_commands[key] = self.commands[key].merge_with(override.commands[key])
            elif key in override.commands:
                # Only override has this key
                merged_commands[key] = override.commands[key]
            else:
                # Only base has this key
                merged_commands[key] = self.commands[key]

        # Merge create_templates (dict - merge keys, with per-key merge)
        merged_create_templates: dict[CreateTemplateName, CreateTemplate] = {}
        all_template_keys = set(self.create_templates.keys()) | set(override.create_templates.keys())
        for key in all_template_keys:
            if key in self.create_templates and key in override.create_templates:
                # Both have this key - merge the templates
                merged_create_templates[key] = self.create_templates[key].merge_with(override.create_templates[key])
            elif key in override.create_templates:
                # Only override has this key
                merged_create_templates[key] = override.create_templates[key]
            else:
                # Only base has this key
                merged_create_templates[key] = self.create_templates[key]

        # Merge pre_command_scripts (dict - override keys take precedence)
        merged_pre_command_scripts = merge_dict_fields(self.pre_command_scripts, override.pre_command_scripts)

        # Merge is_remote_agent_installation_allowed (scalar - override wins if not None)
        merged_is_remote_agent_installation_allowed = (
            override.is_remote_agent_installation_allowed
            if override.is_remote_agent_installation_allowed is not None
            else self.is_remote_agent_installation_allowed
        )

        is_allowed_in_pytest = self.is_allowed_in_pytest
        if override.is_allowed_in_pytest is not None:
            is_allowed_in_pytest = override.is_allowed_in_pytest

        # Merge logging (nested config - use merge_with if override.logging is not None)
        merged_logging = self.logging
        if override.logging is not None:
            merged_logging = self.logging.merge_with(override.logging)

        return self.__class__(
            prefix=merged_prefix,
            default_host_dir=merged_default_host_dir,
            pager=merged_pager,
            unset_vars=merged_unset_vars,
            enabled_backends=merged_enabled_backends,
            agent_types=merged_agent_types,
            providers=merged_providers,
            plugins=merged_plugins,
            disabled_plugins=merged_disabled_plugins,
            commands=merged_commands,
            create_templates=merged_create_templates,
            pre_command_scripts=merged_pre_command_scripts,
            is_remote_agent_installation_allowed=merged_is_remote_agent_installation_allowed,
            logging=merged_logging,
            is_allowed_in_pytest=is_allowed_in_pytest,
        )


class MngrContext(FrozenModel):
    """Context object containing configuration and plugin manager.

    This combines MngrConfig and PluginManager into a single object
    that can be passed through the application, providing access to
    both configuration and plugin hooks.
    """

    model_config = {"arbitrary_types_allowed": True}

    config: MngrConfig = Field(
        description="Configuration for mngr",
    )
    pm: pluggy.PluginManager = Field(
        description="Plugin manager for hooks and backends",
    )
    is_interactive: bool = Field(
        default=False,
        description="Whether the CLI is running in interactive mode (can prompt user for input)",
    )
    profile_dir: Path = Field(
        description="Profile-specific directory for user data (user_id, providers, settings)",
    )
    concurrency_group: ConcurrencyGroup = Field(
        default_factory=lambda: ConcurrencyGroup(name="default"),
        description="Top-level concurrency group for managing spawned processes",
    )

    def get_profile_user_id(self) -> str:
        return get_or_create_user_id(self.profile_dir)


class OutputOptions(FrozenModel):
    """Options for command output formatting and logging."""

    output_format: OutputFormat = Field(
        default=OutputFormat.HUMAN,
        description="Output format for command results",
    )
    console_level: LogLevel = Field(
        default=LogLevel.BUILD,
        description="Log level for console output",
    )
    log_level: LogLevel = Field(
        default=LogLevel.NONE,
        description="Log level for outputting to stderr",
    )
    log_file_path: Path | None = Field(
        default=None,
        description="Override path for log file (if None, uses default ~/.mngr/logs/<timestamp>-<pid>.json)",
    )
    is_log_commands: bool = Field(
        default=True,
        description="Log what commands were executed",
    )
    is_log_command_output: bool = Field(
        default=False,
        description="Log stdout/stderr from executed commands",
    )
    is_log_env_vars: bool = Field(
        default=False,
        description="Log environment variables (security risk)",
    )


# FIXME: this should obviously this should return a concrete type, not a str
def get_or_create_user_id(profile_dir: Path) -> str:
    """Get or create a unique user ID for this mngr profile.

    The user ID is stored in a file in the profile directory. This ID is used
    to namespace Modal apps, ensuring that sandboxes created by different mngr
    installations on a shared Modal account don't interfere with each other.
    """
    user_id_file = profile_dir / USER_ID_FILENAME

    if user_id_file.exists():
        user_id = user_id_file.read_text().strip()
        if os.environ.get("MNGR_USER_ID", ""):
            assert user_id == os.environ.get("MNGR_USER_ID", ""), (
                "MNGR_USER_ID environment variable does not match existing user ID file"
            )
    else:
        if os.environ.get("MNGR_USER_ID", ""):
            user_id = os.environ.get("MNGR_USER_ID", "")
        else:
            # Generate a new user ID
            user_id = uuid4().hex
        user_id_file.write_text(user_id)
    return user_id
