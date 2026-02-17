import importlib.metadata
import os
import re
import tomllib
from enum import auto
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
from imbue.imbue_common.enums import UpperCaseStrEnum
from imbue.imbue_common.frozen_model import FrozenModel
from imbue.imbue_common.logging import log_span
from imbue.imbue_common.pure import pure
from imbue.mngr.cli.common_opts import CommonCliOptions
from imbue.mngr.cli.common_opts import add_common_options
from imbue.mngr.cli.common_opts import setup_command_context
from imbue.mngr.cli.config import ConfigScope
from imbue.mngr.cli.config import get_config_path
from imbue.mngr.cli.config import load_config_file_tomlkit
from imbue.mngr.cli.config import save_config_file
from imbue.mngr.cli.config import set_nested_value
from imbue.mngr.cli.help_formatter import CommandHelpMetadata
from imbue.mngr.cli.help_formatter import add_pager_help_option
from imbue.mngr.cli.help_formatter import register_help_metadata
from imbue.mngr.cli.help_formatter import show_help_with_pager
from imbue.mngr.cli.output_helpers import AbortError
from imbue.mngr.cli.output_helpers import emit_final_json
from imbue.mngr.config.data_types import MngrConfig
from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.config.data_types import OutputOptions
from imbue.mngr.errors import PluginSpecifierError
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

    is_active: bool = False
    fields: str | None = None
    name: str | None = None
    scope: str | None = None


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


class PluginSpecifierType(UpperCaseStrEnum):
    """Classification of a plugin specifier string."""

    LOCAL_PATH = auto()
    GIT_URL = auto()
    PYPI_PACKAGE = auto()


@pure
def _classify_plugin_specifier(specifier: str) -> PluginSpecifierType:
    """Classify a plugin specifier as a local path, git URL, or PyPI package name."""
    if specifier.startswith((".", "/", "~")):
        return PluginSpecifierType.LOCAL_PATH
    if specifier.startswith("git+"):
        return PluginSpecifierType.GIT_URL
    return PluginSpecifierType.PYPI_PACKAGE


@pure
def _parse_pypi_package_name(specifier: str) -> str | None:
    """Extract the canonical package name from a PyPI requirement string.

    Parses specifiers like 'mngr-opencode>=1.0' and returns just the name
    ('mngr-opencode'). Returns None if the specifier is not a valid PyPI
    requirement.
    """
    try:
        req = Requirement(specifier)
    except InvalidRequirement:
        return None
    return req.name


@pure
def _build_uv_pip_install_command(specifier: str, specifier_type: PluginSpecifierType) -> tuple[str, ...]:
    """Build the uv pip install command for a given specifier."""
    match specifier_type:
        case PluginSpecifierType.LOCAL_PATH:
            resolved = str(Path(specifier).expanduser().resolve())
            return ("uv", "pip", "install", "-e", resolved)
        case PluginSpecifierType.GIT_URL:
            return ("uv", "pip", "install", specifier)
        case PluginSpecifierType.PYPI_PACKAGE:
            return ("uv", "pip", "install", specifier)
        case _ as unreachable:
            assert_never(unreachable)


@pure
def _build_uv_pip_uninstall_command(package_name: str) -> tuple[str, ...]:
    """Build the uv pip uninstall command for a given package name."""
    return ("uv", "pip", "uninstall", package_name)


# Matches uv pip install output lines for newly added packages, e.g. " + mngr-opencode==0.1.0"
_UV_INSTALLED_PACKAGE_RE: Final[re.Pattern[str]] = re.compile(r"^\s*\+\s+(\S+)==", re.MULTILINE)


@pure
def _extract_installed_package_name(install_stderr: str) -> str | None:
    """Extract the first newly-installed package name from uv pip install stderr.

    Parses lines like ' + package-name==1.0.0' from uv's output. Returns
    the first match, which for a git URL install is typically the primary package.
    Returns None if no newly-installed package lines are found.
    """
    match = _UV_INSTALLED_PACKAGE_RE.search(install_stderr)
    return match.group(1) if match is not None else None


def _read_package_name_from_pyproject(local_path: str) -> str:
    """Read the package name from a local path's pyproject.toml.

    Raises PluginSpecifierError if the file is missing or has no project.name.
    """
    resolved = Path(local_path).expanduser().resolve()
    pyproject_path = resolved / "pyproject.toml"
    if not pyproject_path.exists():
        raise PluginSpecifierError(f"No pyproject.toml found at '{resolved}' -- cannot determine package name")
    with open(pyproject_path, "rb") as f:
        data = tomllib.load(f)
    name = data.get("project", {}).get("name")
    if not name:
        raise PluginSpecifierError(f"pyproject.toml at '{resolved}' does not have a project.name field")
    return name


def _check_for_mngr_entry_points(package_name: str) -> bool:
    """Check whether an installed package registered any mngr entry points.

    Returns True if entry points were found, False otherwise.
    """
    try:
        dist = importlib.metadata.distribution(package_name)
    except importlib.metadata.PackageNotFoundError:
        return False
    entry_points = dist.entry_points
    return any(ep.group == "mngr" for ep in entry_points)


def _emit_plugin_add_result(
    specifier: str,
    package_name: str,
    has_entry_points: bool,
    output_opts: OutputOptions,
) -> None:
    """Emit the result of a plugin add operation."""
    match output_opts.output_format:
        case OutputFormat.HUMAN:
            logger.info("Installed plugin package '{}'", package_name)
            if not has_entry_points:
                logger.warning(
                    "Package installed but no mngr entry points found -- this package may not be a mngr plugin"
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
            logger.info("Removed plugin package '{}'", package_name)
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
    """Manage available and active plugins.

    View, enable, and disable plugins registered with mngr.

    Examples:

      mngr plugin list

      mngr plugin list --active

      mngr plugin list --fields name,enabled
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
@click.argument("specifier")
@add_common_options
@click.pass_context
def plugin_add(ctx: click.Context, specifier: str, **kwargs: Any) -> None:
    """Install a plugin package.

    SPECIFIER can be a PyPI package name, a local path, or a git URL.

    Local paths (starting with '.', '/', or '~') are installed in editable mode.
    Git URLs must start with 'git+'.

    Examples:

      mngr plugin add mngr-opencode

      mngr plugin add mngr-opencode>=1.0

      mngr plugin add ./my-plugin

      mngr plugin add git+https://github.com/user/mngr-plugin.git
    """
    try:
        _plugin_add_impl(ctx, specifier=specifier)
    except AbortError as e:
        logger.error("Aborted: {}", e.message)
        ctx.exit(1)


@plugin.command(name="remove")
@click.argument("specifier")
@add_common_options
@click.pass_context
def plugin_remove(ctx: click.Context, specifier: str, **kwargs: Any) -> None:
    """Uninstall a plugin package.

    SPECIFIER can be a package name or a local path. For local paths, the
    package name is read from pyproject.toml. Git URLs are not supported --
    use the package name instead (find it with `mngr plugin list`).

    Examples:

      mngr plugin remove mngr-opencode

      mngr plugin remove ./my-plugin
    """
    try:
        _plugin_remove_impl(ctx, specifier=specifier)
    except AbortError as e:
        logger.error("Aborted: {}", e.message)
        ctx.exit(1)


def _resolve_package_name_after_install(
    specifier: str,
    specifier_type: PluginSpecifierType,
    install_stderr: str,
) -> str:
    """Resolve the installed package name from a specifier after installation.

    For PyPI packages, extracts the canonical name from the requirement string.
    For local paths, reads the name from pyproject.toml (falls back to the raw specifier).
    For git URLs, parses the uv install output to find the installed package name.
    """
    match specifier_type:
        case PluginSpecifierType.PYPI_PACKAGE:
            return _parse_pypi_package_name(specifier) or specifier
        case PluginSpecifierType.LOCAL_PATH:
            try:
                return _read_package_name_from_pyproject(specifier)
            except PluginSpecifierError:
                return specifier
        case PluginSpecifierType.GIT_URL:
            return _extract_installed_package_name(install_stderr) or specifier
        case _ as unreachable:
            assert_never(unreachable)


def _plugin_add_impl(ctx: click.Context, *, specifier: str) -> None:
    """Implementation of plugin add command."""
    mngr_ctx, output_opts, _opts = setup_command_context(
        ctx=ctx,
        command_name="plugin",
        command_class=PluginCliOptions,
    )

    specifier_type = _classify_plugin_specifier(specifier)

    # Validate PyPI specifiers early to fail fast before running uv
    if specifier_type == PluginSpecifierType.PYPI_PACKAGE and _parse_pypi_package_name(specifier) is None:
        raise AbortError(
            f"Unrecognized plugin specifier '{specifier}'. Expected one of:\n"
            "  - A PyPI package name (e.g. mngr-opencode, mngr-opencode>=1.0)\n"
            "  - A local path (e.g. ./my-plugin, /path/to/plugin)\n"
            "  - A git URL (e.g. git+https://github.com/user/repo.git)"
        )

    command = _build_uv_pip_install_command(specifier, specifier_type)

    with log_span("Installing plugin package '{}'", specifier):
        try:
            result = mngr_ctx.concurrency_group.run_process_to_completion(command)
        except ProcessError as e:
            raise AbortError(
                f"Failed to install plugin package '{specifier}': {e.stderr.strip() or e.stdout.strip()}",
                original_exception=e,
            ) from e

    resolved_package_name = _resolve_package_name_after_install(specifier, specifier_type, result.stderr)
    has_entry_points = _check_for_mngr_entry_points(resolved_package_name)
    _emit_plugin_add_result(specifier, resolved_package_name, has_entry_points, output_opts)


def _plugin_remove_impl(ctx: click.Context, *, specifier: str) -> None:
    """Implementation of plugin remove command."""
    mngr_ctx, output_opts, _opts = setup_command_context(
        ctx=ctx,
        command_name="plugin",
        command_class=PluginCliOptions,
    )

    specifier_type = _classify_plugin_specifier(specifier)

    # Resolve the package name from the specifier
    match specifier_type:
        case PluginSpecifierType.PYPI_PACKAGE:
            package_name = _parse_pypi_package_name(specifier)
            if package_name is None:
                raise AbortError(
                    f"Unrecognized plugin specifier '{specifier}'. Expected one of:\n"
                    "  - A PyPI package name (e.g. mngr-opencode, mngr-opencode>=1.0)\n"
                    "  - A local path (e.g. ./my-plugin, /path/to/plugin)\n"
                    "  - A git URL (e.g. git+https://github.com/user/repo.git)"
                )
        case PluginSpecifierType.LOCAL_PATH:
            try:
                package_name = _read_package_name_from_pyproject(specifier)
            except PluginSpecifierError as e:
                raise AbortError(str(e)) from e
        case PluginSpecifierType.GIT_URL:
            raise AbortError(
                "Cannot determine the package name from a git URL. "
                "Use the package name instead (find it with `mngr plugin list`)"
            )
        case _ as unreachable:
            assert_never(unreachable)

    command = _build_uv_pip_uninstall_command(package_name)

    with log_span("Removing plugin package '{}'", package_name):
        try:
            mngr_ctx.concurrency_group.run_process_to_completion(command)
        except ProcessError as e:
            raise AbortError(
                f"Failed to remove plugin package '{package_name}': {e.stderr.strip() or e.stdout.strip()}",
                original_exception=e,
            ) from e

    _emit_plugin_remove_result(package_name, output_opts)


# FOLLOWUP: in addition to the above, I also want a sub-command for "mngr plugin search" so that you can easily search across all plugins (once there are a bunch of them)
# FOLLOWUP: in addition to the above, I also want a sub-command for "mngr plugin generate" so that you can easily create your own plugin for basically any functionality you want (and then publish it for others to use or take inspiration from!)


@plugin.command(name="enable")
@click.argument("name")
@click.option(
    "--scope",
    type=click.Choice(["user", "project", "local"], case_sensitive=False),
    default="project",
    show_default=True,
    help="Config scope: user (~/.mngr/profiles/<profile_id>/), project (.mngr/), or local (.mngr/settings.local.toml)",
)
@add_common_options
@click.pass_context
def plugin_enable(ctx: click.Context, **kwargs: Any) -> None:
    """Enable a plugin.

    Sets plugins.<name>.enabled = true in the configuration file at the
    specified scope.

    Examples:

      mngr plugin enable modal

      mngr plugin enable modal --scope user

      mngr plugin enable modal --format json
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
    help="Config scope: user (~/.mngr/profiles/<profile_id>/), project (.mngr/), or local (.mngr/settings.local.toml)",
)
@add_common_options
@click.pass_context
def plugin_disable(ctx: click.Context, **kwargs: Any) -> None:
    """Disable a plugin.

    Sets plugins.<name>.enabled = false in the configuration file at the
    specified scope.

    Examples:

      mngr plugin disable modal

      mngr plugin disable modal --scope user

      mngr plugin disable modal --format json
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
    mngr_ctx, output_opts, opts = setup_command_context(
        ctx=ctx,
        command_name="plugin",
        command_class=PluginCliOptions,
    )

    name = opts.name
    if name is None:
        raise AbortError("Plugin name is required")

    _validate_plugin_name_is_known(name, mngr_ctx)

    root_name = os.environ.get("MNGR_ROOT_NAME", "mngr")
    scope = ConfigScope((opts.scope or "project").upper())
    config_path = get_config_path(scope, root_name, mngr_ctx.profile_dir, mngr_ctx.concurrency_group)

    doc = load_config_file_tomlkit(config_path)
    set_nested_value(doc, f"plugins.{name}.enabled", is_enabled)
    save_config_file(config_path, doc)

    _emit_plugin_toggle_result(name, is_enabled, scope, config_path, output_opts)


def _validate_plugin_name_is_known(name: str, mngr_ctx: MngrContext) -> None:
    """Warn if the plugin name is not registered with the plugin manager.

    This is a soft validation: the user may be pre-configuring a plugin
    before installing it.
    """
    known_names = {n for n, _ in mngr_ctx.pm.list_name_plugin() if n is not None}
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
            logger.info("{} plugin '{}' in {} ({})", action, name, scope.value.lower(), config_path)
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
    name="mngr-plugin",
    one_line_description="Manage available and active plugins",
    synopsis="mngr [plugin|plug] <subcommand> [OPTIONS]",
    description="""Manage available and active plugins.

Install, remove, view, enable, and disable plugins registered with mngr.
Plugins provide agent types, provider backends, CLI commands, and lifecycle hooks.""",
    aliases=("plug",),
    examples=(
        ("List all plugins", "mngr plugin list"),
        ("List only active plugins", "mngr plugin list --active"),
        ("List plugins as JSON", "mngr plugin list --format json"),
        ("Show specific fields", "mngr plugin list --fields name,enabled"),
        ("Install a plugin from PyPI", "mngr plugin add mngr-opencode"),
        ("Install a local plugin", "mngr plugin add ./my-plugin"),
        ("Install a plugin from git", "mngr plugin add git+https://github.com/user/mngr-plugin.git"),
        ("Remove a plugin", "mngr plugin remove mngr-opencode"),
        ("Enable a plugin", "mngr plugin enable modal"),
        ("Disable a plugin", "mngr plugin disable modal --scope user"),
    ),
    see_also=(("config", "Manage mngr configuration"),),
)

register_help_metadata("plugin", _PLUGIN_HELP_METADATA)
for alias in _PLUGIN_HELP_METADATA.aliases:
    register_help_metadata(alias, _PLUGIN_HELP_METADATA)

add_pager_help_option(plugin)
