from collections.abc import Mapping
from collections.abc import Sequence
from typing import Any

import click
import pluggy

from imbue.mngr.api.data_types import OnBeforeCreateArgs
from imbue.mngr.cli.data_types import OptionStackItem
from imbue.mngr.config.data_types import ProviderInstanceConfig
from imbue.mngr.interfaces.agent import AgentInterface
from imbue.mngr.interfaces.host import HostInterface
from imbue.mngr.interfaces.host import OnlineHostInterface
from imbue.mngr.interfaces.provider_backend import ProviderBackendInterface

hookspec = pluggy.HookspecMarker("mngr")


@hookspec
def register_provider_backend() -> tuple[type[ProviderBackendInterface], type[ProviderInstanceConfig]] | None:
    """Register a provider backend with mngr.

    Plugins should implement this hook to register provider backends along with
    their configuration class.

    Return a tuple of (backend_class, config_class) to register a backend,
    or None if not registering a backend.

    The config_class should be a subclass of ProviderInstanceConfig that defines
    the configuration options for this backend.
    """


@hookspec
def register_agent_type() -> tuple[str, type[AgentInterface] | None, type | None] | None:
    """Register an agent type with mngr.

    Types should implement this hook as a static method to register themselves.
    Return a tuple of (agent_type_name, agent_class, config_class) or None.
    - agent_type_name: The string name for this agent type (e.g., "claude", "codex")
    - agent_class: The AgentInterface implementation class (or None to use BaseAgent)
    - config_class: The AgentTypeConfig subclass (or None to use AgentTypeConfig)
    """


@hookspec
def on_agent_created(agent: AgentInterface, host: OnlineHostInterface) -> None:
    """Called after an agent has been created.

    This hook is called after an agent is fully created and started.
    Plugins can use this to perform actions like logging, notifications,
    or custom setup.
    """


@hookspec
def on_agent_destroyed(agent: AgentInterface, host: HostInterface) -> None:
    """Called before an agent is destroyed.

    This hook is called before an agent is destroyed.
    Plugins can use this to perform cleanup or logging.
    """


@hookspec
def on_host_created(host: HostInterface) -> None:
    """Called after a host has been created.

    This hook is called after a host is fully created.
    Plugins can use this to perform custom setup or logging.
    """


@hookspec
def on_host_destroyed(host: HostInterface) -> None:
    """Called before a host is destroyed.

    This hook is called before a host is destroyed.
    Plugins can use this to perform cleanup or logging.
    """


@hookspec
def register_cli_options(command_name: str) -> Mapping[str, list[OptionStackItem]] | None:
    """Register custom CLI options for a mngr subcommand.

    Plugins can implement this hook to add custom command-line options
    to mngr subcommands. This is similar to pytest's pytest_addoption hook.

    Return a mapping of group_name -> list[OptionStackItem], or None if no options
    are being added. If the group already exists on the command, new options will
    be merged into it. If the group is new, a new option group will be created.
    """


@hookspec
def on_load_config(config_dict: dict[str, Any]) -> None:
    """Called when loading configuration, before final validation.

    This hook is called right before MngrConfig.model_validate() is called,
    allowing plugins to dynamically modify the configuration dictionary.

    The config_dict is passed by reference, so plugins can modify it in place.
    Any changes made will be reflected in the final config object.

    Use cases:
    - Dynamically set configuration values based on environment
    - Inject plugin-specific defaults
    - Transform or normalize configuration values
    """


@hookspec
def register_cli_commands() -> Sequence[click.Command] | None:
    """Register custom CLI commands with mngr.

    Plugins can implement this hook to add new top-level commands to mngr.
    Return a sequence of click.Command objects to register, or None if not
    registering any commands.

    Each command will be added to the main mngr CLI group and will be available
    as `mngr <command_name>`. The command's name attribute determines the
    subcommand name.

    Example plugin implementation::

        @hookimpl
        def register_cli_commands() -> Sequence[click.Command] | None:
            return [my_custom_command]

        @click.command()
        @click.option("--example", help="An example option")
        def my_custom_command(example: str) -> None:
            logger.info("Running custom command with: {}", example)
    """


@hookspec
def override_command_options(
    command_name: str,
    command_class: type,
    params: dict[str, Any],
) -> None:
    """Override or modify command options right before the options object is created.

    This hook is called after CLI argument parsing and config defaults have been
    applied, but before the final command options object is instantiated. Plugins
    can use this to mutate or override any command parameter values.

    The params dict contains all parameters that will be passed to the command
    options class constructor. Plugins should modify this dict in place.

    The command_class is provided so plugins can optionally validate their changes
    by attempting to construct the options object (e.g., command_class(**params)).

    Multiple plugins can implement this hook. They are called in registration
    order, and each plugin receives the params as modified by previous plugins.

    Example plugin implementation::

        @hookimpl
        def override_command_options(
            command_name: str,
            command_class: type,
            params: dict[str, Any],
        ) -> None:
            if command_name == "create" and params.get("agent_type") == "claude":
                # Override the model for claude agents
                params["model"] = "opus"
    """


@hookspec
def on_before_create(args: OnBeforeCreateArgs) -> OnBeforeCreateArgs | None:
    """Called at the start of create(), before any work is done.

    This hook allows plugins to inspect and modify the arguments that will be
    used to create an agent. Plugins can modify agent_options, target_host,
    source_path, or create_work_dir by returning a modified OnBeforeCreateArgs.

    Hooks are called in a chain: each hook receives the args as modified by
    previous hooks. Return a modified OnBeforeCreateArgs to change values,
    or return None to pass through unchanged.

    Example plugin implementation::

        @hookimpl
        def on_before_create(args: OnBeforeCreateArgs) -> OnBeforeCreateArgs | None:
            if args.agent_options.agent_type == "claude":
                # Override agent name for claude agents
                new_options = args.agent_options.model_copy(
                    update=to_update_dict(
                        to_update(args.agent_options.field_ref().name, f"claude-{args.agent_options.name}"),
                    )
                )
                return args.model_copy(
                    update=to_update_dict(
                        to_update(args.field_ref().agent_options, new_options),
                    )
                )
            return None
    """
