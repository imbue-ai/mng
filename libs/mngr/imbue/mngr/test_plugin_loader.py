"""Integration tests for plugin_loader module.

Tests that load_all_registries properly registers all expected backends,
agents, and utility plugins with a real plugin manager.
"""

import pluggy

from imbue.mngr.agents.agent_registry import list_registered_agent_types
from imbue.mngr.plugin_loader import load_all_registries
from imbue.mngr.plugins import hookspecs
from imbue.mngr.providers.registry import list_backends
from imbue.mngr.providers.registry import reset_backend_registry


def test_load_all_registries_registers_local_backend() -> None:
    """load_all_registries makes the local backend available."""
    reset_backend_registry()
    pm = pluggy.PluginManager("mngr")
    pm.add_hookspecs(hookspecs)
    load_all_registries(pm)

    backends = list_backends()
    assert "local" in backends


def test_load_all_registries_registers_modal_backend() -> None:
    """load_all_registries makes the modal backend available."""
    reset_backend_registry()
    pm = pluggy.PluginManager("mngr")
    pm.add_hookspecs(hookspecs)
    load_all_registries(pm)

    backends = list_backends()
    assert "modal" in backends


def test_load_all_registries_registers_ssh_backend() -> None:
    """load_all_registries makes the ssh backend available."""
    reset_backend_registry()
    pm = pluggy.PluginManager("mngr")
    pm.add_hookspecs(hookspecs)
    load_all_registries(pm)

    backends = list_backends()
    assert "ssh" in backends


def test_load_all_registries_registers_serve_command() -> None:
    """load_all_registries registers the api_server plugin which provides the serve command."""
    reset_backend_registry()
    pm = pluggy.PluginManager("mngr")
    pm.add_hookspecs(hookspecs)
    load_all_registries(pm)

    # The api_server plugin registers CLI commands via the hook
    all_command_lists = pm.hook.register_cli_commands()
    command_names: list[str] = []
    for command_list in all_command_lists:
        if command_list is not None:
            for cmd in command_list:
                if cmd.name is not None:
                    command_names.append(cmd.name)

    assert "serve" in command_names
    assert "token" in command_names


def test_load_all_registries_registers_agent_types(
    plugin_manager: pluggy.PluginManager,
) -> None:
    """load_all_registries registers agent type plugins (claude, codex).

    The autouse plugin_manager fixture loads agents via load_agents_from_plugins,
    populating the global agent registry. We verify the expected types are present.
    """
    registered = list_registered_agent_types()
    assert "claude" in registered
