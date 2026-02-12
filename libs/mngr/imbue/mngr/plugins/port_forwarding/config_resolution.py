from pathlib import Path

from imbue.mngr.config.data_types import MngrConfig
from imbue.mngr.plugins.port_forwarding.auth import read_or_create_auth_token
from imbue.mngr.plugins.port_forwarding.auth import read_or_create_frps_token
from imbue.mngr.plugins.port_forwarding.data_types import PLUGIN_NAME
from imbue.mngr.plugins.port_forwarding.data_types import PortForwardingConfig
from imbue.mngr.plugins.port_forwarding.data_types import ResolvedPortForwardingConfig
from imbue.mngr.primitives import PluginName

DEFAULT_CONFIG_DIR = Path("~/.config/mngr")


def get_plugin_config_from_mngr_config(config: MngrConfig) -> PortForwardingConfig | None:
    """Extract the port forwarding plugin config from MngrConfig, if present and enabled."""
    plugin_config = config.plugins.get(PluginName(PLUGIN_NAME))
    if plugin_config is None:
        return None
    if not isinstance(plugin_config, PortForwardingConfig):
        return None
    if not plugin_config.enabled:
        return None
    return plugin_config


def resolve_port_forwarding_config(
    plugin_config: PortForwardingConfig,
    config_dir: Path = DEFAULT_CONFIG_DIR,
) -> ResolvedPortForwardingConfig:
    """Resolve a PortForwardingConfig into a ResolvedPortForwardingConfig.

    Optional tokens are read from or created on disk if not explicitly set in config.
    """
    expanded_config_dir = config_dir.expanduser()

    frps_token = plugin_config.frps_token
    if frps_token is None:
        frps_token = read_or_create_frps_token(expanded_config_dir)

    auth_token = plugin_config.auth_token
    if auth_token is None:
        auth_token = read_or_create_auth_token(expanded_config_dir)

    return ResolvedPortForwardingConfig(
        enabled=plugin_config.enabled,
        frps_bind_port=plugin_config.frps_bind_port,
        vhost_http_port=plugin_config.vhost_http_port,
        domain_suffix=plugin_config.domain_suffix,
        frps_token=frps_token,
        auth_token=auth_token,
        frps_config_path=plugin_config.frps_config_path,
    )
