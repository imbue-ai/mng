import click
import pluggy
from click_option_group import OptionGroup

from imbue.mngr.cli.common_opts import TCommand
from imbue.mngr.cli.common_opts import create_group_title_option
from imbue.mngr.cli.common_opts import find_last_option_index_in_group
from imbue.mngr.cli.common_opts import find_option_group
from imbue.mngr.cli.config import config
from imbue.mngr.cli.connect import connect
from imbue.mngr.cli.create import create
from imbue.mngr.cli.destroy import destroy
from imbue.mngr.cli.gc import gc
from imbue.mngr.cli.list import list_command
from imbue.mngr.cli.message import message
from imbue.mngr.cli.pull import pull
from imbue.mngr.cli.push import push
from imbue.mngr.plugins import hookspecs
from imbue.mngr.providers.registry import load_all_registries

# Module-level container for the plugin manager singleton, created lazily.
# Using a dict avoids the need for the 'global' keyword while still allowing module-level state.
_plugin_manager_container: dict[str, pluggy.PluginManager | None] = {"pm": None}


@click.group()
@click.version_option(prog_name="mngr", message="%(prog)s %(version)s")
@click.pass_context
def cli(ctx: click.Context) -> None:
    """
    Initial entry point for mngr CLI commands.

    Makes the plugin manager available in the command context.
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
BUILTIN_COMMANDS: list[click.Command] = [config, connect, create, destroy, gc, list_command, message, pull, push]

for cmd in BUILTIN_COMMANDS:
    cli.add_command(cmd)

# Add command aliases ("c" is a shorthand for "create", "cfg" for "config", "msg" for "message")
cli.add_command(create, name="c")
cli.add_command(config, name="cfg")
cli.add_command(message, name="msg")

# Register plugin commands after built-in commands but before applying CLI options.
# This ordering allows plugins to add CLI options to other plugin commands.
PLUGIN_COMMANDS = _register_plugin_commands()

for cmd in BUILTIN_COMMANDS + PLUGIN_COMMANDS:
    apply_plugin_cli_options(cmd)
