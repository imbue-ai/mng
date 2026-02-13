# Orchestrates loading of all plugin registries at application startup.
#
# This module exists to separate utility plugin loading from the backend registry.
# The backend registry (providers/registry.py) is imported by api/providers.py,
# and the api_server plugin depends on api/providers.py transitively. Keeping both
# in the same module would create a circular import:
#
#     registry -> api_server.plugin -> cli -> app -> api.find -> api.list -> api.providers -> registry
#
# By placing load_all_registries here (a "leaf" module imported only by main.py
# and tests), the cycle is eliminated.
import imbue.mngr.plugins.activity_tracking.plugin as activity_tracking_plugin_module
import imbue.mngr.plugins.api_server.plugin as api_server_plugin_module
import imbue.mngr.plugins.port_forwarding.plugin as port_forwarding_plugin_module
import imbue.mngr.plugins.ttyd.plugin as ttyd_plugin_module
from imbue.mngr.agents.agent_registry import load_agents_from_plugins
from imbue.mngr.providers.registry import load_backends_from_plugins


def _load_utility_plugins(pm) -> None:
    """Register built-in utility plugins (non-agent, non-provider)."""
    pm.register(port_forwarding_plugin_module)
    pm.register(ttyd_plugin_module)
    pm.register(api_server_plugin_module)
    pm.register(activity_tracking_plugin_module)


def load_all_registries(pm) -> None:
    """Load all registries from plugins.

    This is the main entry point for loading all pluggy-based registries.
    Call this once during application startup, before using any registry lookups.
    """
    load_backends_from_plugins(pm)
    load_agents_from_plugins(pm)
    _load_utility_plugins(pm)
