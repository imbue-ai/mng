from collections.abc import Sequence

import click

from imbue.mngr import hookimpl
from imbue.mngr.interfaces.agent import AgentInterface
from imbue.mngr.interfaces.host import OnlineHostInterface
from imbue.mngr.plugins.port_forwarding.cli import auth_command
from imbue.mngr.plugins.port_forwarding.data_types import PortForwardingConfig
from imbue.mngr.plugins.port_forwarding.provisioning import install_frpc_on_host


@hookimpl
def on_agent_created(agent: AgentInterface, host: OnlineHostInterface) -> None:
    """Install frpc and forward-service on the host when an agent is first created.

    This is idempotent -- if frpc is already installed, the provisioning step
    checks for it and skips the install.
    """
    config = _get_plugin_config_or_none()
    if config is None:
        return

    install_frpc_on_host(host=host, config=config)


@hookimpl
def register_cli_commands() -> Sequence[click.Command] | None:
    """Register the 'auth' CLI command for port forwarding authentication."""
    return [auth_command]


def _get_plugin_config_or_none() -> PortForwardingConfig | None:
    """Try to load the port forwarding plugin config, returning None if not configured.

    The config will be read from MngrContext.config.plugins["port_forwarding"]
    once the full plugin config system is wired up.
    """
    return None
