"""Unit tests for port forwarding data types."""

import pytest

from imbue.imbue_common.primitives import PositiveInt
from imbue.mngr.plugins.port_forwarding.data_types import ForwardedService
from imbue.mngr.plugins.port_forwarding.data_types import ForwardedServiceName
from imbue.mngr.plugins.port_forwarding.data_types import PortForwardingConfig


def test_forwarded_service_name_rejects_empty() -> None:
    with pytest.raises(ValueError):
        ForwardedServiceName("")


def test_forwarded_service_name_accepts_valid() -> None:
    name = ForwardedServiceName("web")
    assert str(name) == "web"


def test_port_forwarding_config_has_defaults() -> None:
    config = PortForwardingConfig()
    assert config.frps_bind_port == 7000
    assert config.vhost_http_port == 8080
    assert config.domain_suffix == "mngr.localhost"
    assert config.frps_token is None
    assert config.auth_token is None
    assert config.enabled is True


def test_forwarded_service_is_frozen() -> None:
    service = ForwardedService(
        service_name=ForwardedServiceName("web"),
        local_port=PositiveInt(3000),
        agent_name="alice",
        host_name="dev-box",
        subdomain="web.alice.dev-box",
        url="http://web.alice.dev-box.mngr.localhost:8080",
    )
    assert service.service_name == "web"
    assert service.local_port == 3000
    assert service.url == "http://web.alice.dev-box.mngr.localhost:8080"
