"""Unit tests for frps/frpc config generation."""

from pydantic import SecretStr

from imbue.imbue_common.primitives import PositiveInt
from imbue.mngr.plugins.port_forwarding.config_generation import generate_frpc_base_config
from imbue.mngr.plugins.port_forwarding.config_generation import generate_frpc_full_config
from imbue.mngr.plugins.port_forwarding.config_generation import generate_frpc_proxy_entry
from imbue.mngr.plugins.port_forwarding.config_generation import generate_frps_config
from imbue.mngr.plugins.port_forwarding.data_types import ForwardedService
from imbue.mngr.plugins.port_forwarding.data_types import ForwardedServiceName
from imbue.mngr.plugins.port_forwarding.data_types import PortForwardingConfig


def _make_config() -> PortForwardingConfig:
    return PortForwardingConfig(
        frps_token=SecretStr("test-frps-token"),
        auth_token=SecretStr("test-auth-token"),
    )


def _make_service(
    service_name: str = "web",
    local_port: int = 3000,
    agent_name: str = "alice",
    host_name: str = "dev-box",
) -> ForwardedService:
    subdomain = f"{service_name}.{agent_name}.{host_name}"
    return ForwardedService(
        service_name=ForwardedServiceName(service_name),
        local_port=PositiveInt(local_port),
        agent_name=agent_name,
        host_name=host_name,
        subdomain=subdomain,
        url=f"http://{subdomain}.mngr.localhost:8080",
    )


def test_generate_frps_config_contains_bind_port() -> None:
    config = _make_config()
    result = generate_frps_config(config)
    assert "bindPort = 7000" in result


def test_generate_frps_config_contains_vhost_port() -> None:
    config = _make_config()
    result = generate_frps_config(config)
    assert "vhostHTTPPort = 8080" in result


def test_generate_frps_config_contains_auth_token() -> None:
    config = _make_config()
    result = generate_frps_config(config)
    assert 'token = "test-frps-token"' in result


def test_generate_frpc_base_config_contains_server_address() -> None:
    result = generate_frpc_base_config(
        frps_address="127.0.0.1",
        frps_port=7000,
        frps_token="secret123",
    )
    assert 'serverAddr = "127.0.0.1"' in result
    assert "serverPort = 7000" in result
    assert 'token = "secret123"' in result


def test_generate_frpc_proxy_entry_contains_proxy_fields() -> None:
    service = _make_service()
    result = generate_frpc_proxy_entry(
        service=service,
        domain_suffix="mngr.localhost",
    )
    assert "[[proxies]]" in result
    assert 'name = "web-alice-dev-box"' in result
    assert 'type = "http"' in result
    assert "localPort = 3000" in result
    assert 'customDomains = ["web.alice.dev-box.mngr.localhost"]' in result


def test_generate_frpc_full_config_with_no_services() -> None:
    result = generate_frpc_full_config(
        frps_address="127.0.0.1",
        frps_port=7000,
        frps_token="secret",
        services=[],
        domain_suffix="mngr.localhost",
    )
    assert 'serverAddr = "127.0.0.1"' in result
    assert "[[proxies]]" not in result


def test_generate_frpc_full_config_with_multiple_services() -> None:
    services = [
        _make_service(service_name="web", local_port=3000),
        _make_service(service_name="api", local_port=8000),
    ]
    result = generate_frpc_full_config(
        frps_address="127.0.0.1",
        frps_port=7000,
        frps_token="secret",
        services=services,
        domain_suffix="mngr.localhost",
    )
    assert result.count("[[proxies]]") == 2
    assert "localPort = 3000" in result
    assert "localPort = 8000" in result
