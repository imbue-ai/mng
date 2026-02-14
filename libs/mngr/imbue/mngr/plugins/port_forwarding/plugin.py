from collections.abc import Sequence

import click

from imbue.mngr import hookimpl
from imbue.mngr.config.plugin_registry import register_plugin_config
from imbue.mngr.interfaces.agent import AgentInterface
from imbue.mngr.interfaces.host import OnlineHostInterface
from imbue.mngr.plugins.port_forwarding.cli import auth_command
from imbue.mngr.plugins.port_forwarding.config_resolution import get_plugin_config_from_mngr_config
from imbue.mngr.plugins.port_forwarding.config_resolution import resolve_port_forwarding_config
from imbue.mngr.plugins.port_forwarding.data_types import PLUGIN_NAME
from imbue.mngr.plugins.port_forwarding.data_types import PortForwardingConfig
from imbue.mngr.plugins.port_forwarding.data_types import ResolvedPortForwardingConfig
from imbue.mngr.plugins.port_forwarding.provisioning import install_frpc_on_host

# Register the plugin's typed config class so the TOML loader uses it
# instead of the generic PluginConfig when parsing [plugins.port_forwarding].
register_plugin_config(PLUGIN_NAME, PortForwardingConfig)


@hookimpl
def on_agent_created(agent: AgentInterface, host: OnlineHostInterface) -> None:
    """Install frpc and forward-service on the host when an agent is first created.

    This is idempotent -- if frpc is already installed, the provisioning step
    checks for it and skips the install.
    """
    resolved = _resolve_config_from_agent(agent)
    if resolved is None:
        return

    install_frpc_on_host(host=host, config=resolved)


@hookimpl
def register_cli_commands() -> Sequence[click.Command] | None:
    """Register the 'auth' CLI command for port forwarding authentication."""
    return [auth_command]


def _resolve_config_from_agent(agent: AgentInterface) -> ResolvedPortForwardingConfig | None:
    """Extract and resolve the port forwarding config from an agent's MngrContext."""
    plugin_config = get_plugin_config_from_mngr_config(agent.mngr_ctx.config)
    if plugin_config is None:
        return None

    return resolve_port_forwarding_config(plugin_config)
