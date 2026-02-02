import json
import os
import subprocess
import tomllib
from collections.abc import MutableMapping
from enum import auto
from pathlib import Path
from typing import Any
from typing import assert_never
from typing import cast

import click
import tomlkit
from loguru import logger

from imbue.imbue_common.enums import UpperCaseStrEnum
from imbue.mngr.cli.common_opts import CommonCliOptions
from imbue.mngr.cli.common_opts import add_common_options
from imbue.mngr.cli.common_opts import setup_command_context
from imbue.mngr.cli.help_formatter import CommandHelpMetadata
from imbue.mngr.cli.help_formatter import register_help_metadata
from imbue.mngr.cli.output_helpers import AbortError
from imbue.mngr.cli.output_helpers import emit_final_json
from imbue.mngr.config.data_types import OutputOptions
from imbue.mngr.config.loader import get_or_create_profile_dir
from imbue.mngr.errors import ConfigKeyNotFoundError
from imbue.mngr.errors import ConfigNotFoundError
from imbue.mngr.errors import ConfigStructureError
from imbue.mngr.primitives import OutputFormat
from imbue.mngr.utils.git_utils import find_git_worktree_root


class ConfigScope(UpperCaseStrEnum):
    """Scope for configuration file operations."""

    USER = auto()
    PROJECT = auto()
    LOCAL = auto()


class ConfigCliOptions(CommonCliOptions):
    """Options passed from the CLI to the config command.

    Inherits common options (output_format, quiet, verbose, etc.) from CommonCliOptions.

    Note that this class VERY INTENTIONALLY DOES NOT use Field() decorators with descriptions, defaults, etc.
    For that information, see the click.option() and click.argument() decorators on the config() function itself.
    """

    scope: str | None
    # Arguments used by subcommands (get, set, unset)
    key: str | None = None
    value: str | None = None


def _get_config_path(scope: ConfigScope, root_name: str = "mngr") -> Path:
    """Get the config file path for the given scope."""
    match scope:
        case ConfigScope.USER:
            # User config is in the active profile directory
            base_dir = Path.home() / f".{root_name}"
            # TODO: this function really needs to be passed a MngrContext, which we can use to get the profile_dir out of
            #  We really should not be just randomly making new ones here
            profile_dir = get_or_create_profile_dir(base_dir)
            return profile_dir / "settings.toml"
        case ConfigScope.PROJECT:
            git_root = find_git_worktree_root()
            if git_root is None:
                raise ConfigNotFoundError("No git repository found for project config")
            return git_root / f".{root_name}" / "settings.toml"
        case ConfigScope.LOCAL:
            git_root = find_git_worktree_root()
            if git_root is None:
                raise ConfigNotFoundError("No git repository found for local config")
            return git_root / f".{root_name}" / "settings.local.toml"
        case _ as unreachable:
            assert_never(unreachable)


def _load_config_file(path: Path) -> dict[str, Any]:
    """Load a TOML config file."""
    if not path.exists():
        return {}
    with open(path, "rb") as f:
        return tomllib.load(f)


def _load_config_file_tomlkit(path: Path) -> tomlkit.TOMLDocument:
    """Load a TOML config file using tomlkit for preservation of formatting."""
    if not path.exists():
        return tomlkit.document()
    with open(path) as f:
        return tomlkit.load(f)


def _save_config_file(path: Path, doc: tomlkit.TOMLDocument) -> None:
    """Save a TOML config file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        tomlkit.dump(doc, f)


def _get_nested_value(data: dict[str, Any], key_path: str) -> Any:
    """Get a value from nested dict using dot-separated key path."""
    keys = key_path.split(".")
    current = data
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            raise ConfigKeyNotFoundError(key_path)
        current = current[key]
    return current


def _set_nested_value(doc: tomlkit.TOMLDocument, key_path: str, value: Any) -> None:
    """Set a value in nested tomlkit document using dot-separated key path.

    Works with tomlkit's TOMLDocument and Table types, which both behave like
    MutableMapping at runtime even though their type stubs don't perfectly reflect this.
    """
    keys = key_path.split(".")
    # tomlkit's TOMLDocument and Table are dict subclasses at runtime
    current: MutableMapping[str, Any] = doc
    for key in keys[:-1]:
        if key not in current:
            current[key] = tomlkit.table()
        next_val = current[key]
        if not isinstance(next_val, dict):
            raise ConfigStructureError(f"Cannot set nested key: {key} is not a table")
        # Cast is needed because tomlkit stubs don't reflect that Table is a dict
        current = cast(MutableMapping[str, Any], next_val)
    current[keys[-1]] = value


def _unset_nested_value(doc: tomlkit.TOMLDocument, key_path: str) -> bool:
    """Remove a value from nested tomlkit document using dot-separated key path.

    Returns True if the value was found and removed, False otherwise.

    Works with tomlkit's TOMLDocument and Table types, which both behave like
    MutableMapping at runtime even though their type stubs don't perfectly reflect this.
    """
    keys = key_path.split(".")
    # tomlkit's TOMLDocument and Table are dict subclasses at runtime
    current: MutableMapping[str, Any] = doc
    for key in keys[:-1]:
        if key not in current:
            return False
        next_val = current[key]
        if not isinstance(next_val, dict):
            return False
        # Cast is needed because tomlkit stubs don't reflect that Table is a dict
        current = cast(MutableMapping[str, Any], next_val)
    if keys[-1] in current:
        del current[keys[-1]]
        return True
    return False


def _parse_value(value_str: str) -> Any:
    """Parse a string value into the appropriate type.

    Attempts to parse as JSON first (for booleans, numbers, arrays, objects),
    then falls back to treating it as a string.
    """
    # Try parsing as JSON for proper type handling
    try:
        return json.loads(value_str)
    except json.JSONDecodeError:
        # Not valid JSON, treat as string
        return value_str


def _format_value_for_display(value: Any) -> str:
    """Format a value for human-readable display."""
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, str):
        return value
    return json.dumps(value)


def _flatten_config(config: dict[str, Any], prefix: str = "") -> list[tuple[str, Any]]:
    """Flatten a nested config dict into a list of (key_path, value) tuples."""
    result: list[tuple[str, Any]] = []
    for key, value in config.items():
        full_key = f"{prefix}{key}" if prefix else key
        if isinstance(value, dict):
            result.extend(_flatten_config(value, f"{full_key}."))
        else:
            result.append((full_key, value))
    return result


@click.group(name="config", invoke_without_command=True)
@click.option(
    "--scope",
    type=click.Choice(["user", "project", "local"], case_sensitive=False),
    help="Config scope: user (~/.mngr/profiles/<profile_id>/), project (.mngr/), or local (.mngr/settings.local.toml)",
)
@add_common_options
@click.pass_context
def config(ctx: click.Context, **kwargs: Any) -> None:
    """Manage mngr configuration.

    View, edit, and modify mngr configuration settings at the user, project,
    or local scope.

    Examples:

      mngr config list

      mngr config get prefix

      mngr config set --scope project commands.create.connect false

      mngr config unset commands.create.connect

      mngr config edit --scope user
    """
    # If no subcommand is provided, show help
    if ctx.invoked_subcommand is None:
        logger.info(ctx.get_help())


@config.command(name="list")
@click.option(
    "--scope",
    type=click.Choice(["user", "project", "local"], case_sensitive=False),
    help="Config scope: user (~/.mngr/profiles/<profile_id>/), project (.mngr/), or local (.mngr/settings.local.toml)",
)
@add_common_options
@click.pass_context
def config_list(ctx: click.Context, **kwargs: Any) -> None:
    """List all configuration values.

    Shows all configuration settings from the specified scope, or from the
    merged configuration if no scope is specified.

    Examples:

      mngr config list

      mngr config list --scope user

      mngr config list --format json
    """
    try:
        _config_list_impl(ctx, **kwargs)
    except AbortError as e:
        logger.error("Aborted: {}", e.message)
        ctx.exit(1)


def _config_list_impl(ctx: click.Context, **kwargs: Any) -> None:
    """Implementation of config list command."""
    mngr_ctx, output_opts, opts = setup_command_context(
        ctx=ctx,
        command_name="config",
        command_class=ConfigCliOptions,
    )

    root_name = os.environ.get("MNGR_ROOT_NAME", "mngr")

    if opts.scope:
        # List config from specific scope
        scope = ConfigScope(opts.scope.upper())
        config_path = _get_config_path(scope, root_name)
        config_data = _load_config_file(config_path)
        _emit_config_list(config_data, output_opts, scope, config_path)
    else:
        # List merged config (show what's currently in effect)
        config_data = mngr_ctx.config.model_dump(mode="json")
        _emit_config_list(config_data, output_opts, None, None)


def _emit_config_list(
    config_data: dict[str, Any],
    output_opts: OutputOptions,
    scope: ConfigScope | None,
    config_path: Path | None,
) -> None:
    """Emit the config list output in the appropriate format."""
    match output_opts.output_format:
        case OutputFormat.JSON:
            output = {"config": config_data}
            if scope is not None:
                output["scope"] = scope.value.lower()
            if config_path is not None:
                output["path"] = str(config_path)
            emit_final_json(output)
        case OutputFormat.JSONL:
            output = {"event": "config_list", "config": config_data}
            if scope is not None:
                output["scope"] = scope.value.lower()
            if config_path is not None:
                output["path"] = str(config_path)
            emit_final_json(output)
        case OutputFormat.HUMAN:
            if scope is not None and config_path is not None:
                logger.info("Config from {} ({}):", scope.value.lower(), config_path)
            else:
                logger.info("Merged configuration (all scopes):")
            logger.info("")
            if not config_data:
                logger.info("  (empty)")
            else:
                flattened = _flatten_config(config_data)
                for key, value in sorted(flattened):
                    logger.info("  {} = {}", key, _format_value_for_display(value))
        case _ as unreachable:
            assert_never(unreachable)


@config.command(name="get")
@click.argument("key")
@click.option(
    "--scope",
    type=click.Choice(["user", "project", "local"], case_sensitive=False),
    help="Config scope: user (~/.mngr/profiles/<profile_id>/), project (.mngr/), or local (.mngr/settings.local.toml)",
)
@add_common_options
@click.pass_context
def config_get(ctx: click.Context, key: str, **kwargs: Any) -> None:
    """Get a configuration value.

    Retrieves the value of a specific configuration key. Use dot notation
    for nested keys (e.g., 'commands.create.connect').

    Examples:

      mngr config get prefix

      mngr config get commands.create.connect

      mngr config get logging.console_level --scope user
    """
    try:
        _config_get_impl(ctx, key, **kwargs)
    except AbortError as e:
        logger.error("Aborted: {}", e.message)
        ctx.exit(1)


def _config_get_impl(ctx: click.Context, key: str, **kwargs: Any) -> None:
    """Implementation of config get command."""
    mngr_ctx, output_opts, opts = setup_command_context(
        ctx=ctx,
        command_name="config",
        command_class=ConfigCliOptions,
    )

    root_name = os.environ.get("MNGR_ROOT_NAME", "mngr")

    if opts.scope:
        # Get from specific scope
        scope = ConfigScope(opts.scope.upper())
        config_path = _get_config_path(scope, root_name)
        config_data = _load_config_file(config_path)
    else:
        # Get from merged config
        config_data = mngr_ctx.config.model_dump(mode="json")

    try:
        value = _get_nested_value(config_data, key)
        _emit_config_value(key, value, output_opts)
    except KeyError:
        _emit_key_not_found(key, output_opts)
        ctx.exit(1)


def _emit_config_value(key: str, value: Any, output_opts: OutputOptions) -> None:
    """Emit a config value in the appropriate format."""
    match output_opts.output_format:
        case OutputFormat.JSON:
            emit_final_json({"key": key, "value": value})
        case OutputFormat.JSONL:
            emit_final_json({"event": "config_value", "key": key, "value": value})
        case OutputFormat.HUMAN:
            logger.info("{}", _format_value_for_display(value))
        case _ as unreachable:
            assert_never(unreachable)


def _emit_key_not_found(key: str, output_opts: OutputOptions) -> None:
    """Emit a key not found error in the appropriate format."""
    match output_opts.output_format:
        case OutputFormat.JSON:
            emit_final_json({"error": f"Key not found: {key}", "key": key})
        case OutputFormat.JSONL:
            emit_final_json({"event": "error", "message": f"Key not found: {key}", "key": key})
        case OutputFormat.HUMAN:
            logger.error("Key not found: {}", key)
        case _ as unreachable:
            assert_never(unreachable)


@config.command(name="set")
@click.argument("key")
@click.argument("value")
@click.option(
    "--scope",
    type=click.Choice(["user", "project", "local"], case_sensitive=False),
    default="project",
    show_default=True,
    help="Config scope: user (~/.mngr/profiles/<profile_id>/), project (.mngr/), or local (.mngr/settings.local.toml)",
)
@add_common_options
@click.pass_context
def config_set(ctx: click.Context, key: str, value: str, **kwargs: Any) -> None:
    """Set a configuration value.

    Sets a configuration value at the specified scope. Use dot notation
    for nested keys (e.g., 'commands.create.connect').

    Values are parsed as JSON if possible, otherwise as strings.
    Use 'true'/'false' for booleans, numbers for integers/floats.

    Examples:

      mngr config set prefix "my-"

      mngr config set commands.create.connect false

      mngr config set logging.console_level DEBUG --scope user
    """
    try:
        _config_set_impl(ctx, key, value, **kwargs)
    except AbortError as e:
        logger.error("Aborted: {}", e.message)
        ctx.exit(1)


def _config_set_impl(ctx: click.Context, key: str, value: str, **kwargs: Any) -> None:
    """Implementation of config set command."""
    mngr_ctx, output_opts, opts = setup_command_context(
        ctx=ctx,
        command_name="config",
        command_class=ConfigCliOptions,
    )

    root_name = os.environ.get("MNGR_ROOT_NAME", "mngr")
    scope = ConfigScope((opts.scope or "project").upper())
    config_path = _get_config_path(scope, root_name)

    # Load existing config
    doc = _load_config_file_tomlkit(config_path)

    # Parse and set the value
    parsed_value = _parse_value(value)
    _set_nested_value(doc, key, parsed_value)

    # Save the config
    _save_config_file(config_path, doc)

    _emit_config_set_result(key, parsed_value, scope, config_path, output_opts)


def _emit_config_set_result(
    key: str,
    value: Any,
    scope: ConfigScope,
    config_path: Path,
    output_opts: OutputOptions,
) -> None:
    """Emit the result of a config set operation."""
    match output_opts.output_format:
        case OutputFormat.JSON:
            emit_final_json(
                {
                    "key": key,
                    "value": value,
                    "scope": scope.value.lower(),
                    "path": str(config_path),
                }
            )
        case OutputFormat.JSONL:
            emit_final_json(
                {
                    "event": "config_set",
                    "key": key,
                    "value": value,
                    "scope": scope.value.lower(),
                    "path": str(config_path),
                }
            )
        case OutputFormat.HUMAN:
            logger.info(
                "Set {} = {} in {} ({})", key, _format_value_for_display(value), scope.value.lower(), config_path
            )
        case _ as unreachable:
            assert_never(unreachable)


@config.command(name="unset")
@click.argument("key")
@click.option(
    "--scope",
    type=click.Choice(["user", "project", "local"], case_sensitive=False),
    default="project",
    show_default=True,
    help="Config scope: user (~/.mngr/profiles/<profile_id>/), project (.mngr/), or local (.mngr/settings.local.toml)",
)
@add_common_options
@click.pass_context
def config_unset(ctx: click.Context, key: str, **kwargs: Any) -> None:
    """Remove a configuration value.

    Removes a configuration value from the specified scope. Use dot notation
    for nested keys (e.g., 'commands.create.connect').

    Examples:

      mngr config unset commands.create.connect

      mngr config unset logging.console_level --scope user
    """
    try:
        _config_unset_impl(ctx, key, **kwargs)
    except AbortError as e:
        logger.error("Aborted: {}", e.message)
        ctx.exit(1)


def _config_unset_impl(ctx: click.Context, key: str, **kwargs: Any) -> None:
    """Implementation of config unset command."""
    mngr_ctx, output_opts, opts = setup_command_context(
        ctx=ctx,
        command_name="config",
        command_class=ConfigCliOptions,
    )

    root_name = os.environ.get("MNGR_ROOT_NAME", "mngr")
    scope = ConfigScope((opts.scope or "project").upper())
    config_path = _get_config_path(scope, root_name)

    if not config_path.exists():
        _emit_key_not_found(key, output_opts)
        ctx.exit(1)

    # Load existing config
    doc = _load_config_file_tomlkit(config_path)

    # Remove the value
    if _unset_nested_value(doc, key):
        # Save the config
        _save_config_file(config_path, doc)
        _emit_config_unset_result(key, scope, config_path, output_opts)
    else:
        _emit_key_not_found(key, output_opts)
        ctx.exit(1)


def _emit_config_unset_result(
    key: str,
    scope: ConfigScope,
    config_path: Path,
    output_opts: OutputOptions,
) -> None:
    """Emit the result of a config unset operation."""
    match output_opts.output_format:
        case OutputFormat.JSON:
            emit_final_json(
                {
                    "key": key,
                    "scope": scope.value.lower(),
                    "path": str(config_path),
                }
            )
        case OutputFormat.JSONL:
            emit_final_json(
                {
                    "event": "config_unset",
                    "key": key,
                    "scope": scope.value.lower(),
                    "path": str(config_path),
                }
            )
        case OutputFormat.HUMAN:
            logger.info("Removed {} from {} ({})", key, scope.value.lower(), config_path)
        case _ as unreachable:
            assert_never(unreachable)


@config.command(name="edit")
@click.option(
    "--scope",
    type=click.Choice(["user", "project", "local"], case_sensitive=False),
    default="project",
    show_default=True,
    help="Config scope: user (~/.mngr/profiles/<profile_id>/), project (.mngr/), or local (.mngr/settings.local.toml)",
)
@add_common_options
@click.pass_context
def config_edit(ctx: click.Context, **kwargs: Any) -> None:
    """Open configuration file in editor.

    Opens the configuration file for the specified scope in your default
    editor (from $EDITOR or $VISUAL environment variable, or 'vi' as fallback).

    If the config file doesn't exist, it will be created with an empty template.

    Examples:

      mngr config edit

      mngr config edit --scope user

      mngr config edit --scope local
    """
    try:
        _config_edit_impl(ctx, **kwargs)
    except AbortError as e:
        logger.error("Aborted: {}", e.message)
        ctx.exit(1)


def _config_edit_impl(ctx: click.Context, **kwargs: Any) -> None:
    """Implementation of config edit command."""
    mngr_ctx, output_opts, opts = setup_command_context(
        ctx=ctx,
        command_name="config",
        command_class=ConfigCliOptions,
    )

    root_name = os.environ.get("MNGR_ROOT_NAME", "mngr")
    scope = ConfigScope((opts.scope or "project").upper())
    config_path = _get_config_path(scope, root_name)

    # Create the config file if it doesn't exist
    if not config_path.exists():
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(_get_config_template())

    # Get the editor
    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR") or "vi"

    match output_opts.output_format:
        case OutputFormat.HUMAN:
            logger.info("Opening {} in {}...", config_path, editor)
        case OutputFormat.JSON | OutputFormat.JSONL:
            pass
        case _ as unreachable:
            assert_never(unreachable)

    # Open the editor
    try:
        subprocess.run([editor, str(config_path)], check=True)
    except subprocess.CalledProcessError as e:
        logger.error("Editor exited with error: {}", e.returncode)
        ctx.exit(e.returncode)
    except FileNotFoundError:
        logger.error("Editor not found: {}", editor)
        logger.error("Set $EDITOR or $VISUAL environment variable to your preferred editor")
        ctx.exit(1)

    match output_opts.output_format:
        case OutputFormat.JSON:
            emit_final_json(
                {
                    "scope": scope.value.lower(),
                    "path": str(config_path),
                }
            )
        case OutputFormat.JSONL:
            emit_final_json(
                {
                    "event": "config_edited",
                    "scope": scope.value.lower(),
                    "path": str(config_path),
                }
            )
        case OutputFormat.HUMAN:
            pass
        case _ as unreachable:
            assert_never(unreachable)


def _get_config_template() -> str:
    """Get a template for a new config file."""
    return """# mngr configuration file
# See 'mngr help --config' for available options

# Resource naming prefix
# prefix = "mngr-"

# Default host directory
# default_host_dir = "~/.mngr"

# Custom agent types
# [agent_types.my_claude]
# parent_type = "claude"
# cli_args = "--env CLAUDE_MODEL=opus"
# permissions = ["github", "npm"]

# Provider instances
# [providers.my-docker]
# backend = "docker"

# Command defaults
# [commands.create]
# new_branch_prefix = "agent/"
# connect = false

# Logging configuration
# [logging]
# console_level = "INFO"
# file_level = "DEBUG"
"""


@config.command(name="path")
@click.option(
    "--scope",
    type=click.Choice(["user", "project", "local"], case_sensitive=False),
    help="Config scope: user (~/.mngr/profiles/<profile_id>/), project (.mngr/), or local (.mngr/settings.local.toml)",
)
@add_common_options
@click.pass_context
def config_path(ctx: click.Context, **kwargs: Any) -> None:
    """Show configuration file paths.

    Shows the paths to configuration files. If --scope is specified, shows
    only that scope's path. Otherwise shows all paths and whether they exist.

    Examples:

      mngr config path

      mngr config path --scope user
    """
    try:
        _config_path_impl(ctx, **kwargs)
    except AbortError as e:
        logger.error("Aborted: {}", e.message)
        ctx.exit(1)


def _config_path_impl(ctx: click.Context, **kwargs: Any) -> None:
    """Implementation of config path command."""
    mngr_ctx, output_opts, opts = setup_command_context(
        ctx=ctx,
        command_name="config",
        command_class=ConfigCliOptions,
    )

    root_name = os.environ.get("MNGR_ROOT_NAME", "mngr")

    if opts.scope:
        # Show specific scope
        scope = ConfigScope(opts.scope.upper())
        try:
            config_path = _get_config_path(scope, root_name)
            _emit_single_path(scope, config_path, output_opts)
        except ConfigNotFoundError as e:
            match output_opts.output_format:
                case OutputFormat.JSON:
                    emit_final_json({"error": str(e), "scope": scope.value.lower()})
                case OutputFormat.JSONL:
                    emit_final_json({"event": "error", "message": str(e), "scope": scope.value.lower()})
                case OutputFormat.HUMAN:
                    logger.error("{}", e)
                case _ as unreachable:
                    assert_never(unreachable)
            ctx.exit(1)
    else:
        # Show all scopes
        paths: list[dict[str, Any]] = []
        for scope in ConfigScope:
            try:
                config_path = _get_config_path(scope, root_name)
                paths.append(
                    {
                        "scope": scope.value.lower(),
                        "path": str(config_path),
                        "exists": config_path.exists(),
                    }
                )
            except ConfigNotFoundError:
                paths.append(
                    {
                        "scope": scope.value.lower(),
                        "path": None,
                        "exists": False,
                        "error": f"No git repository found for {scope.value.lower()} config",
                    }
                )
        _emit_all_paths(paths, output_opts)


def _emit_single_path(scope: ConfigScope, config_path: Path, output_opts: OutputOptions) -> None:
    """Emit a single config path."""
    match output_opts.output_format:
        case OutputFormat.JSON:
            emit_final_json(
                {
                    "scope": scope.value.lower(),
                    "path": str(config_path),
                    "exists": config_path.exists(),
                }
            )
        case OutputFormat.JSONL:
            emit_final_json(
                {
                    "event": "config_path",
                    "scope": scope.value.lower(),
                    "path": str(config_path),
                    "exists": config_path.exists(),
                }
            )
        case OutputFormat.HUMAN:
            logger.info("{}", config_path)
        case _ as unreachable:
            assert_never(unreachable)


def _emit_all_paths(paths: list[dict[str, Any]], output_opts: OutputOptions) -> None:
    """Emit all config paths."""
    match output_opts.output_format:
        case OutputFormat.JSON:
            emit_final_json({"paths": paths})
        case OutputFormat.JSONL:
            emit_final_json({"event": "config_paths", "paths": paths})
        case OutputFormat.HUMAN:
            for path_info in paths:
                scope = path_info["scope"]
                path = path_info.get("path")
                exists = path_info.get("exists", False)
                if path:
                    status = "exists" if exists else "not found"
                    logger.info("{}: {} ({})", scope, path, status)
                else:
                    error = path_info.get("error", "unavailable")
                    logger.info("{}: {}", scope, error)
        case _ as unreachable:
            assert_never(unreachable)


# Register help metadata for git-style help formatting
_CONFIG_HELP_METADATA = CommandHelpMetadata(
    name="mngr-config",
    one_line_description="Manage mngr configuration",
    synopsis="mngr [config|cfg] <subcommand> [OPTIONS]",
    description="""Manage mngr configuration.

View, edit, and modify mngr configuration settings at the user, project, or
local level. Much like a simpler version of `git config`, this command allows
you to manage configuration settings at different scopes.

Configuration is stored in TOML files:
- User: ~/.mngr/settings.toml
- Project: .mngr/settings.toml (in your git root)
- Local: .mngr/settings.local.toml (git-ignored, for local overrides)""",
    aliases=("cfg",),
    examples=(
        ("List all configuration values", "mngr config list"),
        ("Get a specific value", "mngr config get provider.docker.image"),
        ("Set a value at user scope", "mngr config set --user provider.docker.image my-image:latest"),
        ("Edit config in your editor", "mngr config edit"),
        ("Show config file paths", "mngr config path"),
    ),
    see_also=(("create", "Create a new agent with configuration"),),
)

register_help_metadata("config", _CONFIG_HELP_METADATA)
# Also register under alias for consistent help output
for alias in _CONFIG_HELP_METADATA.aliases:
    register_help_metadata(alias, _CONFIG_HELP_METADATA)
