from typing import Any
from typing import Final
from typing import assert_never

import click
from loguru import logger
from pydantic import Field
from tabulate import tabulate

from imbue.imbue_common.frozen_model import FrozenModel
from imbue.imbue_common.pure import pure
from imbue.mngr.cli.common_opts import CommonCliOptions
from imbue.mngr.cli.common_opts import add_common_options
from imbue.mngr.cli.common_opts import setup_command_context
from imbue.mngr.cli.help_formatter import CommandHelpMetadata
from imbue.mngr.cli.help_formatter import register_help_metadata
from imbue.mngr.cli.output_helpers import AbortError
from imbue.mngr.cli.output_helpers import emit_final_json
from imbue.mngr.config.data_types import MngrConfig
from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.config.data_types import OutputOptions
from imbue.mngr.primitives import OutputFormat
from imbue.mngr.primitives import PluginName

# Default fields to display
DEFAULT_FIELDS: Final[tuple[str, ...]] = ("name", "version", "description", "enabled")


class PluginCliOptions(CommonCliOptions):
    """Options passed from the CLI to the plugin command.

    Inherits common options (output_format, quiet, verbose, etc.) from CommonCliOptions.

    Note that this class VERY INTENTIONALLY DOES NOT use Field() decorators with descriptions, defaults, etc.
    For that information, see the click.option() and click.argument() decorators on the plugin() function itself.
    """

    is_active: bool
    fields: str | None


class PluginInfo(FrozenModel):
    """Information about a discovered plugin."""

    name: str = Field(description="Plugin name")
    version: str | None = Field(default=None, description="Plugin version from distribution metadata")
    description: str | None = Field(default=None, description="Plugin description from distribution metadata")
    is_enabled: bool = Field(description="Whether the plugin is currently enabled")


@pure
def _is_plugin_enabled(name: str, config: MngrConfig) -> bool:
    """Check whether a plugin is enabled based on config.

    A plugin is disabled if:
    1. Its name is in the disabled_plugins set, OR
    2. It appears in the plugins dict with enabled=False
    """
    if name in config.disabled_plugins:
        return False
    plugin_key = PluginName(name)
    if plugin_key in config.plugins and not config.plugins[plugin_key].enabled:
        return False
    return True


def _gather_plugin_info(mngr_ctx: MngrContext) -> list[PluginInfo]:
    """Discover plugins from the plugin manager and return sorted info.

    Uses pm.list_name_plugin() for all registered plugins and
    pm.list_plugin_distinfo() for distribution metadata (version, description).
    """
    pm = mngr_ctx.pm

    # Build a map of plugin object id -> dist metadata from externally installed plugins
    dist_info_by_plugin: dict[int, Any] = {}
    for plugin_obj, dist in pm.list_plugin_distinfo():
        dist_info_by_plugin[id(plugin_obj)] = dist

    # Gather info for all registered plugins
    plugin_info_by_name: dict[str, PluginInfo] = {}
    for name, plugin_obj in pm.list_name_plugin():
        if name is None:
            continue
        # Skip internal pluggy marker plugins
        if name.startswith("_"):
            continue

        version: str | None = None
        description: str | None = None

        # Check for distribution metadata
        dist = dist_info_by_plugin.get(id(plugin_obj))
        if dist is not None:
            metadata = dist.metadata
            version = metadata.get("version")
            description = metadata.get("summary")

        is_enabled = _is_plugin_enabled(name, mngr_ctx.config)

        plugin_info_by_name[name] = PluginInfo(
            name=name,
            version=version,
            description=description,
            is_enabled=is_enabled,
        )

    return sorted(plugin_info_by_name.values(), key=lambda p: p.name)


@pure
def _get_field_value(plugin: PluginInfo, field: str) -> str:
    """Get a display value for a plugin field."""
    match field:
        case "name":
            return plugin.name
        case "version":
            return plugin.version or "-"
        case "description":
            return plugin.description or "-"
        case "enabled":
            return str(plugin.is_enabled).lower()
        case _:
            return "-"


def _emit_plugin_list(
    plugins: list[PluginInfo],
    output_opts: OutputOptions,
    fields: tuple[str, ...],
) -> None:
    """Emit the plugin list in the appropriate output format."""
    match output_opts.output_format:
        case OutputFormat.HUMAN:
            _emit_plugin_list_human(plugins, fields)
        case OutputFormat.JSON:
            _emit_plugin_list_json(plugins, fields)
        case OutputFormat.JSONL:
            _emit_plugin_list_jsonl(plugins, fields)
        case _ as unreachable:
            assert_never(unreachable)


def _emit_plugin_list_human(plugins: list[PluginInfo], fields: tuple[str, ...]) -> None:
    """Emit plugin list in human-readable table format."""
    if not plugins:
        logger.info("No plugins found.")
        return

    headers = [f.upper() for f in fields]
    rows: list[list[str]] = []
    for p in plugins:
        rows.append([_get_field_value(p, f) for f in fields])

    table = tabulate(rows, headers=headers, tablefmt="plain")
    logger.info("\n" + table)


def _emit_plugin_list_json(plugins: list[PluginInfo], fields: tuple[str, ...]) -> None:
    """Emit plugin list in JSON format."""
    plugin_dicts = [{f: _get_field_value(p, f) for f in fields} for p in plugins]
    emit_final_json({"plugins": plugin_dicts})


def _emit_plugin_list_jsonl(plugins: list[PluginInfo], fields: tuple[str, ...]) -> None:
    """Emit plugin list in JSONL format (one line per plugin)."""
    for p in plugins:
        emit_final_json({f: _get_field_value(p, f) for f in fields})


@pure
def _parse_fields(fields_str: str | None) -> tuple[str, ...]:
    """Parse a comma-separated fields string into a tuple of field names."""
    if fields_str is None:
        return DEFAULT_FIELDS
    return tuple(f.strip() for f in fields_str.split(",") if f.strip())


@click.group(name="plugin", invoke_without_command=True)
@add_common_options
@click.pass_context
def plugin(ctx: click.Context, **kwargs: Any) -> None:
    """Manage available and active plugins.

    View, enable, and disable plugins registered with mngr.

    Examples:

      mngr plugin list

      mngr plugin list --active

      mngr plugin list --fields name,enabled
    """
    if ctx.invoked_subcommand is None:
        logger.info(ctx.get_help())


@plugin.command(name="list")
@click.option(
    "--active",
    "is_active",
    is_flag=True,
    default=False,
    help="Show only currently enabled plugins",
)
@click.option(
    "--fields",
    type=str,
    default=None,
    help="Comma-separated list of fields to display (name, version, description, enabled)",
)
@add_common_options
@click.pass_context
def plugin_list(ctx: click.Context, **kwargs: Any) -> None:
    """List discovered plugins.

    Shows all plugins registered with mngr, including built-in plugins
    and any externally installed plugins.

    Examples:

      mngr plugin list

      mngr plugin list --active

      mngr plugin list --format json

      mngr plugin list --fields name,enabled
    """
    try:
        _plugin_list_impl(ctx, **kwargs)
    except AbortError as e:
        logger.error("Aborted: {}", e.message)
        ctx.exit(1)


def _plugin_list_impl(ctx: click.Context, **kwargs: Any) -> None:
    """Implementation of plugin list command."""
    mngr_ctx, output_opts, opts = setup_command_context(
        ctx=ctx,
        command_name="plugin",
        command_class=PluginCliOptions,
    )

    all_plugins = _gather_plugin_info(mngr_ctx)

    # Filter to active plugins if requested
    filtered_plugins = [p for p in all_plugins if p.is_enabled] if opts.is_active else all_plugins

    fields = _parse_fields(opts.fields)
    _emit_plugin_list(filtered_plugins, output_opts, fields)


@plugin.command(name="add")
@click.argument("name")
@add_common_options
@click.pass_context
def plugin_add(ctx: click.Context, name: str, **kwargs: Any) -> None:
    """Add a plugin. [future]"""
    raise NotImplementedError("'mngr plugin add' is not yet implemented")


@plugin.command(name="remove")
@click.argument("name")
@add_common_options
@click.pass_context
def plugin_remove(ctx: click.Context, name: str, **kwargs: Any) -> None:
    """Remove a plugin. [future]"""
    raise NotImplementedError("'mngr plugin remove' is not yet implemented")


@plugin.command(name="enable")
@click.argument("name")
@add_common_options
@click.pass_context
def plugin_enable(ctx: click.Context, name: str, **kwargs: Any) -> None:
    """Enable a plugin. [future]"""
    raise NotImplementedError("'mngr plugin enable' is not yet implemented")


@plugin.command(name="disable")
@click.argument("name")
@add_common_options
@click.pass_context
def plugin_disable(ctx: click.Context, name: str, **kwargs: Any) -> None:
    """Disable a plugin. [future]"""
    raise NotImplementedError("'mngr plugin disable' is not yet implemented")


# Register help metadata for git-style help formatting
_PLUGIN_HELP_METADATA = CommandHelpMetadata(
    name="mngr-plugin",
    one_line_description="Manage available and active plugins",
    synopsis="mngr [plugin|plug] <subcommand> [OPTIONS]",
    description="""Manage available and active plugins.

View, enable, and disable plugins registered with mngr. Plugins provide
agent types, provider backends, CLI commands, and lifecycle hooks.

Currently, only the `list` subcommand is fully implemented. The `add`,
`remove`, `enable`, and `disable` subcommands are placeholders for future
functionality.""",
    aliases=("plug",),
    examples=(
        ("List all plugins", "mngr plugin list"),
        ("List only active plugins", "mngr plugin list --active"),
        ("List plugins as JSON", "mngr plugin list --format json"),
        ("Show specific fields", "mngr plugin list --fields name,enabled"),
    ),
    see_also=(("config", "Manage mngr configuration"),),
)

register_help_metadata("plugin", _PLUGIN_HELP_METADATA)
for alias in _PLUGIN_HELP_METADATA.aliases:
    register_help_metadata(alias, _PLUGIN_HELP_METADATA)
