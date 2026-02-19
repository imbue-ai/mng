import importlib.metadata
import json
import os
import sys
import tomllib
from pathlib import Path
from typing import Any
from typing import Final
from typing import assert_never

import click
from loguru import logger
from packaging.requirements import InvalidRequirement
from packaging.requirements import Requirement
from pydantic import Field
from tabulate import tabulate

from imbue.concurrency_group.errors import ProcessError
from imbue.imbue_common.frozen_model import FrozenModel
from imbue.imbue_common.logging import log_span
from imbue.imbue_common.pure import pure
from imbue.mng.cli.common_opts import CommonCliOptions
from imbue.mng.cli.common_opts import add_common_options
from imbue.mng.cli.common_opts import setup_command_context
from imbue.mng.cli.config import ConfigScope
from imbue.mng.cli.config import get_config_path
from imbue.mng.cli.config import load_config_file_tomlkit
from imbue.mng.cli.config import save_config_file
from imbue.mng.cli.config import set_nested_value
from imbue.mng.cli.help_formatter import CommandHelpMetadata
from imbue.mng.cli.help_formatter import add_pager_help_option
from imbue.mng.cli.help_formatter import register_help_metadata
from imbue.mng.cli.help_formatter import show_help_with_pager
from imbue.mng.cli.output_helpers import AbortError
from imbue.mng.cli.output_helpers import emit_final_json
from imbue.mng.cli.output_helpers import emit_format_template_lines
from imbue.mng.cli.output_helpers import write_human_line
from imbue.mng.config.data_types import MngConfig
from imbue.mng.config.data_types import MngContext
from imbue.mng.config.data_types import OutputOptions
from imbue.mng.errors import PluginSpecifierError
from imbue.mng.primitives import OutputFormat
from imbue.mng.primitives import PluginName

# Default fields to display
DEFAULT_FIELDS: Final[tuple[str, ...]] = ("name", "version", "description", "enabled")


class PluginCliOptions(CommonCliOptions):
    """Options passed from the CLI to the plugin command.

    Inherits common options (output_format, quiet, verbose, etc.) from CommonCliOptions.

    Note that this class VERY INTENTIONALLY DOES NOT use Field() decorators with descriptions, defaults, etc.
    For that information, see the click.option() and click.argument() decorators on the plugin() function itself.
    """

    is_active: bool = False
    fields: str | None = None
    name: str | None = None
    scope: str | None = None
    path: str | None = None
    git: str | None = None


class PluginInfo(FrozenModel):
    """Information about a discovered plugin."""

    name: str = Field(description="Plugin name")
    version: str | None = Field(default=None, description="Plugin version from distribution metadata")
    description: str | None = Field(default=None, description="Plugin description from distribution metadata")
    is_enabled: bool = Field(description="Whether the plugin is currently enabled")


@pure
def _is_plugin_enabled(name: str, config: MngConfig) -> bool:
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


def _gather_plugin_info(mng_ctx: MngContext) -> list[PluginInfo]:
    """Discover plugins from the plugin manager and return sorted info.

    Uses pm.list_name_plugin() for all registered plugins and
    pm.list_plugin_distinfo() for distribution metadata (version, description).
    """
    pm = mng_ctx.pm

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

        is_enabled = _is_plugin_enabled(name, mng_ctx.config)

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
    if output_opts.format_template is not None:
        items = [{f: _get_field_value(p, f) for f in DEFAULT_FIELDS} for p in plugins]
        emit_format_template_lines(output_opts.format_template, items)
        return
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
        write_human_line("No plugins found.")
        return

    headers = [f.upper() for f in fields]
    rows: list[list[str]] = []
    for p in plugins:
        rows.append([_get_field_value(p, f) for f in fields])

    table = tabulate(rows, headers=headers, tablefmt="plain")
    write_human_line("\n" + table)


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


@pure
def _parse_pypi_package_name(specifier: str) -> str | None:
    """Extract the canonical package name from a PyPI requirement string.

    Parses specifiers like 'mng-opencode>=1.0' and returns just the name
    ('mng-opencode'). Returns None if the specifier is not a valid PyPI
    requirement.
    """
    try:
        req = Requirement(specifier)
    except InvalidRequirement:
        return None
    return req.name


def _build_uv_pip_install_command_for_path(local_path: str) -> tuple[str, ...]:
    """Build the uv pip install command for a local path (editable mode)."""
    resolved = str(Path(local_path).expanduser().resolve())
    return ("uv", "pip", "install", "--python", sys.executable, "-e", resolved)


@pure
def _build_uv_pip_install_command_for_name_or_url(specifier: str) -> tuple[str, ...]:
    """Build the uv pip install command for a PyPI name or git URL."""
    return ("uv", "pip", "install", "--python", sys.executable, specifier)


@pure
def _build_uv_pip_uninstall_command(package_name: str) -> tuple[str, ...]:
    """Build the uv pip uninstall command for a given package name."""
    return ("uv", "pip", "uninstall", "--python", sys.executable, package_name)


def _get_installed_package_names(concurrency_group: Any) -> set[str]:
    """Get the set of currently installed package names via `uv pip list --format json`."""
    result = concurrency_group.run_process_to_completion(
        ("uv", "pip", "list", "--python", sys.executable, "--format", "json")
    )
    packages = json.loads(result.stdout)
    return {pkg["name"] for pkg in packages}


def _read_package_name_from_pyproject(local_path: str) -> str:
    """Read the package name from a local path's pyproject.toml.

    Raises PluginSpecifierError if the file is missing or has no project.name.
    """
    resolved = Path(local_path).expanduser().resolve()
    pyproject_path = resolved / "pyproject.toml"
    if not pyproject_path.exists():
        raise PluginSpecifierError(f"No pyproject.toml found at '{resolved}' -- cannot determine package name")
    with pyproject_path.open("rb") as f:
        data = tomllib.load(f)
    name = data.get("project", {}).get("name")
    if not name:
        raise PluginSpecifierError(f"pyproject.toml at '{resolved}' does not have a project.name field")
    return name


def _check_for_mng_entry_points(package_name: str) -> bool:
    """Check whether an installed package registered any mng entry points.

    Returns True if entry points were found, False otherwise.
    """
    try:
        dist = importlib.metadata.distribution(package_name)
    except importlib.metadata.PackageNotFoundError:
        return False
    entry_points = dist.entry_points
    return any(ep.group == "mng" for ep in entry_points)


def _emit_plugin_add_result(
    specifier: str,
    package_name: str,
    has_entry_points: bool,
    output_opts: OutputOptions,
) -> None:
    """Emit the result of a plugin add operation."""
    match output_opts.output_format:
        case OutputFormat.HUMAN:
            write_human_line("Installed plugin package '{}'", package_name)
            if not has_entry_points:
                logger.warning(
                    "Package installed but no mng entry points found -- this package may not be a mng plugin"
                )
        case OutputFormat.JSON:
            emit_final_json(
                {
                    "specifier": specifier,
                    "package": package_name,
                    "has_entry_points": has_entry_points,
                }
            )
        case OutputFormat.JSONL:
            emit_final_json(
                {
                    "event": "plugin_added",
                    "specifier": specifier,
                    "package": package_name,
                    "has_entry_points": has_entry_points,
                }
            )
        case _ as unreachable:
            assert_never(unreachable)


def _emit_plugin_remove_result(
    package_name: str,
    output_opts: OutputOptions,
) -> None:
    """Emit the result of a plugin remove operation."""
    match output_opts.output_format:
        case OutputFormat.HUMAN:
            write_human_line("Removed plugin package '{}'", package_name)
        case OutputFormat.JSON:
            emit_final_json(
                {
                    "package": package_name,
                }
            )
        case OutputFormat.JSONL:
            emit_final_json(
                {
                    "event": "plugin_removed",
                    "package": package_name,
                }
            )
        case _ as unreachable:
            assert_never(unreachable)


@click.group(name="plugin", invoke_without_command=True)
@add_common_options
@click.pass_context
def plugin(ctx: click.Context, **kwargs: Any) -> None:
    """Manage available and active plugins. [experimental]

    Install, remove, view, enable, and disable plugins registered with mng.

    Examples:

      mng plugin list

      mng plugin list --active

      mng plugin list --fields name,enabled
    """
    if ctx.invoked_subcommand is None:
        show_help_with_pager(ctx, ctx.command, None)


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
    """List discovered plugins. [experimental]

    Shows all plugins registered with mng, including built-in plugins
    and any externally installed plugins.

    Supports custom format templates via --format. Available fields:
    name, version, description, enabled.

    Examples:

      mng plugin list

      mng plugin list --active

      mng plugin list --format json

      mng plugin list --fields name,enabled

      mng plugin list --format '{name}\\t{enabled}'
    """
    try:
        _plugin_list_impl(ctx, **kwargs)
    except AbortError as e:
        logger.error("Aborted: {}", e.message)
        ctx.exit(1)


def _plugin_list_impl(ctx: click.Context, **kwargs: Any) -> None:
    """Implementation of plugin list command."""
    mng_ctx, output_opts, opts = setup_command_context(
        ctx=ctx,
        command_name="plugin",
        command_class=PluginCliOptions,
        is_format_template_supported=True,
    )

    all_plugins = _gather_plugin_info(mng_ctx)

    # Filter to active plugins if requested
    filtered_plugins = [p for p in all_plugins if p.is_enabled] if opts.is_active else all_plugins

    fields = _parse_fields(opts.fields)
    _emit_plugin_list(filtered_plugins, output_opts, fields)


@plugin.command(name="add")
@click.argument("name", required=False, default=None)
@click.option("--path", default=None, help="Install from a local path (editable mode)")
@click.option("--git", default=None, help="Install from a git URL")
@add_common_options
@click.pass_context
def plugin_add(ctx: click.Context, **kwargs: Any) -> None:
    """Install a plugin package. [experimental]

    Provide exactly one of NAME (positional), --path, or --git.

    Examples:

      mng plugin add mng-pair

      mng plugin add mng-pair>=1.0

      mng plugin add --path ./my-plugin

      mng plugin add --git https://github.com/user/mng-plugin.git
    """
    try:
        _plugin_add_impl(ctx)
    except AbortError as e:
        logger.error("Aborted: {}", e.message)
        ctx.exit(1)


@plugin.command(name="remove")
@click.argument("name", required=False, default=None)
@click.option("--path", default=None, help="Remove by local path (reads package name from pyproject.toml)")
@add_common_options
@click.pass_context
def plugin_remove(ctx: click.Context, **kwargs: Any) -> None:
    """Uninstall a plugin package. [experimental]

    Provide exactly one of NAME (positional) or --path. For local paths,
    the package name is read from pyproject.toml.

    Examples:

      mng plugin remove mng-pair

      mng plugin remove --path ./my-plugin
    """
    try:
        _plugin_remove_impl(ctx)
    except AbortError as e:
        logger.error("Aborted: {}", e.message)
        ctx.exit(1)


class _PypiSource(FrozenModel):
    """Plugin source: a PyPI package name (possibly with version constraint)."""

    name: str = Field(description="PyPI package specifier (e.g. 'mng-opencode>=1.0')")


class _PathSource(FrozenModel):
    """Plugin source: a local filesystem path."""

    path: str = Field(description="Local filesystem path to the plugin package")


class _GitSource(FrozenModel):
    """Plugin source: a git URL."""

    url: str = Field(description="Git repository URL for the plugin package")


_AddSource = _PypiSource | _PathSource | _GitSource
_RemoveSource = _PypiSource | _PathSource


@pure
def _parse_add_source(opts: PluginCliOptions) -> _AddSource:
    """Parse and validate the plugin source for an add command.

    Exactly one of name, --path, or --git must be provided.
    """
    source_count = sum(x is not None for x in (opts.name, opts.path, opts.git))
    if source_count == 0:
        raise AbortError("Provide exactly one of NAME, --path, or --git")
    if source_count > 1:
        raise AbortError("NAME, --path, and --git are mutually exclusive")

    if opts.path is not None:
        return _PathSource(path=opts.path)
    if opts.git is not None:
        return _GitSource(url=opts.git)

    assert opts.name is not None
    if _parse_pypi_package_name(opts.name) is None:
        raise AbortError(f"Invalid package name '{opts.name}'")
    return _PypiSource(name=opts.name)


@pure
def _parse_remove_source(opts: PluginCliOptions) -> _RemoveSource:
    """Parse and validate the plugin source for a remove command.

    Exactly one of name or --path must be provided.
    """
    source_count = sum(x is not None for x in (opts.name, opts.path))
    if source_count == 0:
        raise AbortError("Provide exactly one of NAME or --path")
    if source_count > 1:
        raise AbortError("NAME and --path are mutually exclusive")

    if opts.path is not None:
        return _PathSource(path=opts.path)

    assert opts.name is not None
    if _parse_pypi_package_name(opts.name) is None:
        raise AbortError(f"Invalid package name '{opts.name}'")
    return _PypiSource(name=opts.name)


def _plugin_add_impl(ctx: click.Context) -> None:
    """Implementation of plugin add command."""
    mng_ctx, output_opts, opts = setup_command_context(
        ctx=ctx,
        command_name="plugin",
        command_class=PluginCliOptions,
    )

    source = _parse_add_source(opts)

    # Build the install command and determine the display specifier
    match source:
        case _PathSource(path=path):
            specifier = path
            command = _build_uv_pip_install_command_for_path(path)
        case _GitSource(url=url):
            specifier = url
            command = _build_uv_pip_install_command_for_name_or_url(url)
        case _PypiSource(name=name):
            specifier = name
            command = _build_uv_pip_install_command_for_name_or_url(name)
        case _ as unreachable:
            assert_never(unreachable)

    # For git installs, snapshot installed packages before install so we can diff afterward
    packages_before: set[str] | None = None
    if isinstance(source, _GitSource):
        packages_before = _get_installed_package_names(mng_ctx.concurrency_group)

    with log_span("Installing plugin package '{}'", specifier):
        try:
            mng_ctx.concurrency_group.run_process_to_completion(command)
        except ProcessError as e:
            raise AbortError(
                f"Failed to install plugin package '{specifier}': {e.stderr.strip() or e.stdout.strip()}",
                original_exception=e,
            ) from e

    # Resolve the canonical package name from the install
    match source:
        case _PypiSource(name=name):
            resolved_package_name = _parse_pypi_package_name(name) or name
        case _PathSource(path=path):
            try:
                resolved_package_name = _read_package_name_from_pyproject(path)
            except PluginSpecifierError:
                logger.debug("Could not read package name from pyproject.toml at '{}', using raw path", path)
                resolved_package_name = path
        case _GitSource(url=url):
            assert packages_before is not None
            packages_after = _get_installed_package_names(mng_ctx.concurrency_group)
            new_packages = packages_after - packages_before
            resolved_package_name = next(iter(new_packages)) if new_packages else url
        case _ as unreachable:
            assert_never(unreachable)

    has_entry_points = _check_for_mng_entry_points(resolved_package_name)
    _emit_plugin_add_result(specifier, resolved_package_name, has_entry_points, output_opts)


def _plugin_remove_impl(ctx: click.Context) -> None:
    """Implementation of plugin remove command."""
    mng_ctx, output_opts, opts = setup_command_context(
        ctx=ctx,
        command_name="plugin",
        command_class=PluginCliOptions,
    )

    source = _parse_remove_source(opts)

    match source:
        case _PathSource(path=path):
            try:
                package_name = _read_package_name_from_pyproject(path)
            except PluginSpecifierError as e:
                raise AbortError(str(e)) from e
        case _PypiSource(name=name):
            # _parse_remove_source already validated the name; this extracts the canonical form
            package_name = _parse_pypi_package_name(name) or name
        case _ as unreachable:
            assert_never(unreachable)

    # Verify the package is actually installed before trying to uninstall
    try:
        importlib.metadata.distribution(package_name)
    except importlib.metadata.PackageNotFoundError:
        raise AbortError(f"Package '{package_name}' is not installed") from None

    command = _build_uv_pip_uninstall_command(package_name)

    with log_span("Removing plugin package '{}'", package_name):
        try:
            mng_ctx.concurrency_group.run_process_to_completion(command)
        except ProcessError as e:
            raise AbortError(
                f"Failed to remove plugin package '{package_name}': {e.stderr.strip() or e.stdout.strip()}",
                original_exception=e,
            ) from e

    _emit_plugin_remove_result(package_name, output_opts)


# FOLLOWUP: in addition to the above, I also want a sub-command for "mng plugin search" so that you can easily search across all plugins (once there are a bunch of them)
# FOLLOWUP: in addition to the above, I also want a sub-command for "mng plugin generate" so that you can easily create your own plugin for basically any functionality you want (and then publish it for others to use or take inspiration from!)


@plugin.command(name="enable")
@click.argument("name")
@click.option(
    "--scope",
    type=click.Choice(["user", "project", "local"], case_sensitive=False),
    default="project",
    show_default=True,
    help="Config scope: user (~/.mng/profiles/<profile_id>/), project (.mng/), or local (.mng/settings.local.toml)",
)
@add_common_options
@click.pass_context
def plugin_enable(ctx: click.Context, **kwargs: Any) -> None:
    """Enable a plugin. [experimental]

    Sets plugins.<name>.enabled = true in the configuration file at the
    specified scope.

    Examples:

      mng plugin enable modal

      mng plugin enable modal --scope user

      mng plugin enable modal --format json
    """
    try:
        _plugin_enable_impl(ctx, **kwargs)
    except AbortError as e:
        logger.error("Aborted: {}", e.message)
        ctx.exit(1)


@plugin.command(name="disable")
@click.argument("name")
@click.option(
    "--scope",
    type=click.Choice(["user", "project", "local"], case_sensitive=False),
    default="project",
    show_default=True,
    help="Config scope: user (~/.mng/profiles/<profile_id>/), project (.mng/), or local (.mng/settings.local.toml)",
)
@add_common_options
@click.pass_context
def plugin_disable(ctx: click.Context, **kwargs: Any) -> None:
    """Disable a plugin. [experimental]

    Sets plugins.<name>.enabled = false in the configuration file at the
    specified scope.

    Examples:

      mng plugin disable modal

      mng plugin disable modal --scope user

      mng plugin disable modal --format json
    """
    try:
        _plugin_disable_impl(ctx, **kwargs)
    except AbortError as e:
        logger.error("Aborted: {}", e.message)
        ctx.exit(1)


def _plugin_enable_impl(ctx: click.Context, **kwargs: Any) -> None:
    """Implementation of plugin enable command."""
    _plugin_set_enabled_impl(ctx, is_enabled=True)


def _plugin_disable_impl(ctx: click.Context, **kwargs: Any) -> None:
    """Implementation of plugin disable command."""
    _plugin_set_enabled_impl(ctx, is_enabled=False)


def _plugin_set_enabled_impl(ctx: click.Context, *, is_enabled: bool) -> None:
    """Shared implementation for plugin enable/disable commands."""
    mng_ctx, output_opts, opts = setup_command_context(
        ctx=ctx,
        command_name="plugin",
        command_class=PluginCliOptions,
    )

    name = opts.name
    if name is None:
        raise AbortError("Plugin name is required")

    _validate_plugin_name_is_known(name, mng_ctx)

    root_name = os.environ.get("MNG_ROOT_NAME", "mng")
    scope = ConfigScope((opts.scope or "project").upper())
    config_path = get_config_path(scope, root_name, mng_ctx.profile_dir, mng_ctx.concurrency_group)

    doc = load_config_file_tomlkit(config_path)
    set_nested_value(doc, f"plugins.{name}.enabled", is_enabled)
    save_config_file(config_path, doc)

    _emit_plugin_toggle_result(name, is_enabled, scope, config_path, output_opts)


def _validate_plugin_name_is_known(name: str, mng_ctx: MngContext) -> None:
    """Warn if the plugin name is not registered with the plugin manager.

    This is a soft validation: the user may be pre-configuring a plugin
    before installing it.
    """
    known_names = {n for n, _ in mng_ctx.pm.list_name_plugin() if n is not None}
    if name not in known_names:
        logger.warning("Plugin '{}' is not currently registered; setting will apply when it is installed", name)


def _emit_plugin_toggle_result(
    name: str,
    is_enabled: bool,
    scope: ConfigScope,
    config_path: Path,
    output_opts: OutputOptions,
) -> None:
    """Emit the result of a plugin enable/disable operation."""
    match output_opts.output_format:
        case OutputFormat.HUMAN:
            action = "Enabled" if is_enabled else "Disabled"
            write_human_line("{} plugin '{}' in {} ({})", action, name, scope.value.lower(), config_path)
        case OutputFormat.JSON:
            emit_final_json(
                {
                    "plugin": name,
                    "enabled": is_enabled,
                    "scope": scope.value.lower(),
                    "path": str(config_path),
                }
            )
        case OutputFormat.JSONL:
            emit_final_json(
                {
                    "event": "plugin_toggled",
                    "plugin": name,
                    "enabled": is_enabled,
                    "scope": scope.value.lower(),
                    "path": str(config_path),
                }
            )
        case _ as unreachable:
            assert_never(unreachable)


# Register help metadata for git-style help formatting
_PLUGIN_HELP_METADATA = CommandHelpMetadata(
    name="mng-plugin",
    one_line_description="Manage available and active plugins [experimental]",
    synopsis="mng [plugin|plug] <subcommand> [OPTIONS]",
    description="""Manage available and active plugins.

Install, remove, view, enable, and disable plugins registered with mng.
Plugins provide agent types, provider backends, CLI commands, and lifecycle hooks.""",
    aliases=("plug",),
    examples=(
        ("List all plugins", "mng plugin list"),
        ("List only active plugins", "mng plugin list --active"),
        ("List plugins as JSON", "mng plugin list --format json"),
        ("Show specific fields", "mng plugin list --fields name,enabled"),
        ("Install a plugin from PyPI", "mng plugin add mng-pair"),
        ("Install a local plugin", "mng plugin add --path ./my-plugin"),
        ("Install a plugin from git", "mng plugin add --git https://github.com/user/mng-plugin.git"),
        ("Remove a plugin", "mng plugin remove mng-pair"),
        ("Enable a plugin", "mng plugin enable modal"),
        ("Disable a plugin", "mng plugin disable modal --scope user"),
    ),
    see_also=(("config", "Manage mng configuration"),),
)

register_help_metadata("plugin", _PLUGIN_HELP_METADATA)
for alias in _PLUGIN_HELP_METADATA.aliases:
    register_help_metadata(alias, _PLUGIN_HELP_METADATA)

add_pager_help_option(plugin)
