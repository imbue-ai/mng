import bdb
from typing import Any

import click
import pluggy
from click.shell_completion import CompletionItem
from click_option_group import OptionGroup

from imbue.imbue_common.model_update import to_update
from imbue.mngr.cli.ask import ask
from imbue.mngr.cli.cleanup import cleanup
from imbue.mngr.cli.clone import clone
from imbue.mngr.cli.common_opts import TCommand
from imbue.mngr.cli.common_opts import create_group_title_option
from imbue.mngr.cli.common_opts import find_last_option_index_in_group
from imbue.mngr.cli.common_opts import find_option_group
from imbue.mngr.cli.config import config
from imbue.mngr.cli.connect import connect
from imbue.mngr.cli.create import create
from imbue.mngr.cli.destroy import destroy
from imbue.mngr.cli.exec import exec_command
from imbue.mngr.cli.gc import gc
from imbue.mngr.cli.help_formatter import get_help_metadata
from imbue.mngr.cli.help_formatter import register_help_metadata
from imbue.mngr.cli.issue_reporting import handle_not_implemented_error
from imbue.mngr.cli.issue_reporting import handle_unexpected_error
from imbue.mngr.cli.limit import limit
from imbue.mngr.cli.list import list_command
from imbue.mngr.cli.logs import logs
from imbue.mngr.cli.message import message
from imbue.mngr.cli.migrate import migrate
from imbue.mngr.cli.pair import pair
from imbue.mngr.cli.plugin import plugin as plugin_command
from imbue.mngr.cli.provision import provision
from imbue.mngr.cli.pull import pull
from imbue.mngr.cli.push import push
from imbue.mngr.cli.rename import rename
from imbue.mngr.cli.snapshot import snapshot
from imbue.mngr.cli.start import start
from imbue.mngr.cli.stop import stop
from imbue.mngr.errors import BaseMngrError
from imbue.mngr.plugins import hookspecs
from imbue.mngr.providers.registry import get_all_provider_args_help_sections
from imbue.mngr.providers.registry import load_all_registries

# Module-level container for the plugin manager singleton, created lazily.
# Using a dict avoids the need for the 'global' keyword while still allowing module-level state.
_plugin_manager_container: dict[str, pluggy.PluginManager | None] = {"pm": None}

# Command aliases - maps canonical command names to their aliases
# This is used by the help formatter to display aliases
COMMAND_ALIASES: dict[str, list[str]] = {
    "create": ["c"],
    "cleanup": ["clean"],
    "config": ["cfg"],
    "destroy": ["rm"],
    "exec": ["x"],
    "message": ["msg"],
    "list": ["ls"],
    "connect": ["conn"],
    "provision": ["prov"],
    "stop": ["s"],
    "plugin": ["plug"],
    "limit": ["lim"],
    "rename": ["mv"],
    "snapshot": ["snap"],
}

# Build reverse mapping: alias -> canonical name
_ALIAS_TO_CANONICAL: dict[str, str] = {}
for canonical, aliases in COMMAND_ALIASES.items():
    for alias in aliases:
        _ALIAS_TO_CANONICAL[alias] = canonical


class AliasAwareGroup(click.Group):
    """Custom click.Group that shows aliases inline with commands in --help."""

    def invoke(self, ctx: click.Context) -> Any:
        try:
            return super().invoke(ctx)
        except NotImplementedError as e:
            handle_not_implemented_error(e)
        except (click.ClickException, click.Abort, click.exceptions.Exit, BaseMngrError, bdb.BdbQuit):
            raise
        except Exception as e:
            if ctx.meta.get("is_error_reporting_enabled", False):
                handle_unexpected_error(e)
            raise

    def format_commands(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        """Write the command list with aliases shown inline."""
        commands: list[tuple[str, click.Command]] = []
        for subcommand in self.list_commands(ctx):
            cmd = self.get_command(ctx, subcommand)
            if cmd is None or cmd.hidden:
                continue
            # Skip alias entries - we'll show them with the main command
            if subcommand in _ALIAS_TO_CANONICAL:
                continue
            commands.append((subcommand, cmd))

        if not commands:
            return

        # Calculate max width for alignment
        limit = formatter.width - 6 - max(len(cmd[0]) for cmd in commands)

        rows: list[tuple[str, str]] = []
        for subcommand, cmd in commands:
            help_text = cmd.get_short_help_str(limit=limit)
            # Add aliases if this command has them
            aliases = COMMAND_ALIASES.get(subcommand, [])
            if aliases:
                subcommand = ", ".join([subcommand] + aliases)
            rows.append((subcommand, help_text))

        if rows:
            with formatter.section("Commands"):
                formatter.write_dl(rows)

    def shell_complete(self, ctx: click.Context, incomplete: str) -> list[CompletionItem]:
        completions = super().shell_complete(ctx, incomplete)
        completed_names = {item.value for item in completions}
        return [
            item
            for item in completions
            if item.value not in _ALIAS_TO_CANONICAL or _ALIAS_TO_CANONICAL[item.value] not in completed_names
        ]


@click.command(cls=AliasAwareGroup)
@click.version_option(prog_name="mngr", message="%(prog)s %(version)s")
@click.pass_context
def cli(ctx: click.Context) -> None:
    """
    Initial entry point for mngr CLI commands.
    """
    # expose the plugin manager in the command context so that all commands have access to it
    # This uses the singleton that was already created during command registration
    pm = get_or_create_plugin_manager()
    ctx.obj = pm


def _register_plugin_commands() -> list[click.Command]:
    """Register CLI commands from plugins.

    This function is called during module initialization to add any commands
    that plugins have registered via the register_cli_commands hook.

    Returns the list of plugin commands that were registered.
    """
    pm = get_or_create_plugin_manager()
    plugin_commands: list[click.Command] = []

    # Call the hook to get command lists from all plugins
    all_command_lists = pm.hook.register_cli_commands()

    for command_list in all_command_lists:
        if command_list is None:
            continue
        for command in command_list:
            if command.name is None:
                continue
            # Add the plugin command to the CLI group
            cli.add_command(command)
            plugin_commands.append(command)

    return plugin_commands


# Apply plugin-registered CLI options to ALL commands (built-in and plugin).
# This must happen after all commands are added but before the CLI is invoked.
def apply_plugin_cli_options(command: TCommand, command_name: str | None = None) -> TCommand:
    """Apply plugin-registered CLI options to a click command.

    Plugin options are organized into option groups. If a group already exists
    on the command, new options are merged into it. Otherwise, a new group is
    created with a title header for nice help output.
    """
    pm = get_or_create_plugin_manager()
    name = command_name or command.name

    if name is None:
        return command

    # Call the hook to get option mappings from all plugins
    # Each plugin returns a dict of group_name -> list[OptionStackItem]
    all_option_mappings = pm.hook.register_cli_options(command_name=name)

    for option_mapping in all_option_mappings:
        if option_mapping is None:
            continue

        for group_name, option_specs in option_mapping.items():
            existing_group = find_option_group(command, group_name)

            if existing_group is not None:
                # Add options to existing group after the last option in that group
                insert_index = find_last_option_index_in_group(command, existing_group) + 1
                for option_spec in option_specs:
                    click_option = option_spec.to_click_option(group=existing_group)
                    # Register option with the group for proper help rendering
                    existing_group._options[command.callback][click_option.name] = click_option
                    command.params.insert(insert_index, click_option)
                    insert_index += 1
            else:
                # Create new group with title option for help rendering
                new_group = OptionGroup(group_name)
                title_option = create_group_title_option(new_group)
                command.params.append(title_option)

                for option_spec in option_specs:
                    click_option = option_spec.to_click_option(group=new_group)
                    # Register option with the group for proper help rendering
                    new_group._options[command.callback][click_option.name] = click_option
                    command.params.append(click_option)

    return command


def create_plugin_manager() -> pluggy.PluginManager:
    """
    Initializes the plugin manager and loads all plugin registries.

    This should only really be called once from the main command (or during testing).
    """
    # Create plugin manager and load registries first (needed for config parsing)
    pm = pluggy.PluginManager("mngr")
    pm.add_hookspecs(hookspecs)

    # Automatically discover and load plugins registered via setuptools entry points.
    # External packages can register hooks by adding an entry point for the "mngr" group.
    pm.load_setuptools_entrypoints("mngr")

    # load all classes defined by plugins so they are available later
    load_all_registries(pm)

    return pm


def get_or_create_plugin_manager() -> pluggy.PluginManager:
    """
    Get or create the module-level plugin manager singleton.

    This is used during CLI initialization to apply plugin-registered options
    to commands before argument parsing happens. The singleton ensures that
    plugins are only loaded once even if this is called multiple times.
    """
    if _plugin_manager_container["pm"] is None:
        _plugin_manager_container["pm"] = create_plugin_manager()
    return _plugin_manager_container["pm"]


def reset_plugin_manager() -> None:
    """
    Reset the module-level plugin manager singleton.

    This is primarily useful for testing to ensure a fresh plugin manager
    is created for each test.
    """
    _plugin_manager_container["pm"] = None


# Add built-in commands to the CLI group
BUILTIN_COMMANDS: list[click.Command] = [
    ask,
    create,
    cleanup,
    destroy,
    exec_command,
    list_command,
    logs,
    connect,
    message,
    pair,
    provision,
    pull,
    push,
    rename,
    start,
    stop,
    limit,
    snapshot,
    config,
    gc,
    plugin_command,
]

for cmd in BUILTIN_COMMANDS:
    cli.add_command(cmd)

# Add command aliases
cli.add_command(create, name="c")
cli.add_command(cleanup, name="clean")
cli.add_command(config, name="cfg")
cli.add_command(destroy, name="rm")
cli.add_command(exec_command, name="x")
cli.add_command(message, name="msg")
cli.add_command(list_command, name="ls")
cli.add_command(connect, name="conn")
cli.add_command(plugin_command, name="plug")
cli.add_command(provision, name="prov")
cli.add_command(limit, name="lim")
cli.add_command(rename, name="mv")
cli.add_command(snapshot, name="snap")

# Add clone as a standalone command (not in BUILTIN_COMMANDS since it uses
# UNPROCESSED args and delegates to create, which already has plugin options applied)
cli.add_command(clone)
cli.add_command(migrate)

# Register plugin commands after built-in commands but before applying CLI options.
# This ordering allows plugins to add CLI options to other plugin commands.
PLUGIN_COMMANDS = _register_plugin_commands()

for cmd in BUILTIN_COMMANDS + PLUGIN_COMMANDS:
    apply_plugin_cli_options(cmd)


def _update_create_help_with_provider_args() -> None:
    """Update the create command's help metadata with provider-specific build/start args help.

    This must be called after backends are loaded so that all provider backends
    are registered and their help text is available.
    """
    provider_sections = get_all_provider_args_help_sections()
    for command_name in ("create", "c"):
        existing_metadata = get_help_metadata(command_name)
        if existing_metadata is None:
            continue
        updated_metadata = existing_metadata.model_copy_update(
            to_update(
                existing_metadata.field_ref().additional_sections,
                existing_metadata.additional_sections + provider_sections,
            ),
        )
        register_help_metadata(command_name, updated_metadata)


_update_create_help_with_provider_args()
