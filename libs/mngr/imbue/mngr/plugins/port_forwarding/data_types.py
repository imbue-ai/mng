from pathlib import Path
from typing import Final

from pydantic import Field
from pydantic import SecretStr

from imbue.imbue_common.frozen_model import FrozenModel
from imbue.imbue_common.primitives import NonEmptyStr
from imbue.imbue_common.primitives import PositiveInt
from imbue.mngr.config.data_types import PluginConfig

PLUGIN_NAME: Final[str] = "port_forwarding"

DEFAULT_FRPS_BIND_PORT: Final[int] = 7000
DEFAULT_VHOST_HTTP_PORT: Final[int] = 8080
DEFAULT_DOMAIN_SUFFIX: Final[str] = "mngr.localhost"


class ForwardedServiceName(NonEmptyStr):
    """Name for a forwarded service (e.g. 'web', 'terminal', 'api')."""

    ...


class PortForwardingConfig(PluginConfig):
    """Configuration for the port forwarding plugin.

    Tokens are optional in the config file -- if not specified, they will be
    auto-generated and persisted to the config directory on first use. See
    resolve_port_forwarding_config() for the resolution logic.
    """

    frps_bind_port: PositiveInt = Field(
        default=PositiveInt(DEFAULT_FRPS_BIND_PORT),
        description="Port where frps listens for frpc connections",
    )
    vhost_http_port: PositiveInt = Field(
        default=PositiveInt(DEFAULT_VHOST_HTTP_PORT),
        description="Port where frps serves HTTP vhost routing",
    )
    domain_suffix: str = Field(
        default=DEFAULT_DOMAIN_SUFFIX,
        description="Domain suffix for forwarded service URLs (e.g. 'mngr.localhost')",
    )
    frps_token: SecretStr | None = Field(
        default=None,
        description="Shared secret token for frpc-to-frps authentication (auto-generated if not set)",
    )
    auth_token: SecretStr | None = Field(
        default=None,
        description="Token for authenticating browser/programmatic access (auto-generated if not set)",
    )
    frps_config_path: Path = Field(
        default=Path("~/.config/mngr/frps.toml"),
        description="Path to the frps configuration file",
    )


class ResolvedPortForwardingConfig(FrozenModel):
    """PortForwardingConfig with all optional fields resolved to concrete values.

    This is the type used at runtime -- tokens are guaranteed to be present.
    """

    enabled: bool
    frps_bind_port: PositiveInt
    vhost_http_port: PositiveInt
    domain_suffix: str
    frps_token: SecretStr
    auth_token: SecretStr
    frps_config_path: Path


class ForwardedService(FrozenModel):
    """A port-forwarded service registered by an agent."""

    service_name: ForwardedServiceName = Field(
        description="Name of the forwarded service (e.g. 'web', 'terminal')",
    )
    local_port: PositiveInt = Field(
        description="Port on the remote host where the service is running",
    )
    agent_name: str = Field(
        description="Name of the agent that owns this service",
    )
    host_name: str = Field(
        description="Name of the host where the agent runs",
    )
    subdomain: str = Field(
        description="Full subdomain for this service (e.g. 'web.alice.dev-box')",
    )
    url: str = Field(
        description="Full URL for accessing this service (e.g. 'http://web.alice.dev-box.mngr.localhost:8080')",
    )
