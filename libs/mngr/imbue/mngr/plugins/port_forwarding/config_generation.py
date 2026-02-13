from collections.abc import Sequence

from imbue.imbue_common.pure import pure
from imbue.mngr.plugins.port_forwarding.data_types import ForwardedService
from imbue.mngr.plugins.port_forwarding.data_types import PortForwardingConfig


@pure
def generate_frps_config(config: PortForwardingConfig) -> str:
    """Generate the frps.toml configuration file content."""
    return (
        f"bindPort = {config.frps_bind_port}\n"
        f"vhostHTTPPort = {config.vhost_http_port}\n"
        "\n"
        "[auth]\n"
        'method = "token"\n'
        f'token = "{config.frps_token.get_secret_value()}"\n'
    )


@pure
def generate_frpc_base_config(
    frps_address: str,
    frps_port: int,
    frps_token: str,
) -> str:
    """Generate the base frpc.toml configuration (server connection section)."""
    return (
        f'serverAddr = "{frps_address}"\n'
        f"serverPort = {frps_port}\n"
        "\n"
        "[auth]\n"
        'method = "token"\n'
        f'token = "{frps_token}"\n'
    )


@pure
def generate_frpc_proxy_entry(
    service: ForwardedService,
    domain_suffix: str,
) -> str:
    """Generate a single [[proxies]] entry for frpc.toml."""
    proxy_name = service.subdomain.replace(".", "-")
    custom_domain = f"{service.subdomain}.{domain_suffix}"
    return (
        "[[proxies]]\n"
        f'name = "{proxy_name}"\n'
        'type = "http"\n'
        f"localPort = {service.local_port}\n"
        f'customDomains = ["{custom_domain}"]\n'
    )


@pure
def generate_frpc_full_config(
    frps_address: str,
    frps_port: int,
    frps_token: str,
    services: Sequence[ForwardedService],
    domain_suffix: str,
) -> str:
    """Generate the complete frpc.toml configuration."""
    base = generate_frpc_base_config(
        frps_address=frps_address,
        frps_port=frps_port,
        frps_token=frps_token,
    )
    proxy_entries = [generate_frpc_proxy_entry(service=service, domain_suffix=domain_suffix) for service in services]
    return base + "\n" + "\n".join(proxy_entries) if proxy_entries else base
