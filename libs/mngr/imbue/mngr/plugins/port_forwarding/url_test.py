"""Unit tests for URL computation functions."""

from imbue.mngr.plugins.port_forwarding.data_types import ForwardedServiceName
from imbue.mngr.plugins.port_forwarding.url import build_forwarded_service
from imbue.mngr.plugins.port_forwarding.url import compute_service_url
from imbue.mngr.plugins.port_forwarding.url import compute_subdomain
from imbue.mngr.plugins.port_forwarding.url import sanitize_name_for_subdomain


def test_sanitize_name_lowercases() -> None:
    assert sanitize_name_for_subdomain("MyAgent") == "myagent"


def test_sanitize_name_replaces_underscores_with_hyphens() -> None:
    assert sanitize_name_for_subdomain("my_agent") == "my-agent"


def test_sanitize_name_replaces_dots_with_hyphens() -> None:
    assert sanitize_name_for_subdomain("my.agent") == "my-agent"


def test_sanitize_name_collapses_consecutive_hyphens() -> None:
    assert sanitize_name_for_subdomain("my--agent") == "my-agent"


def test_sanitize_name_strips_leading_trailing_hyphens() -> None:
    assert sanitize_name_for_subdomain("-my-agent-") == "my-agent"


def test_sanitize_name_returns_unnamed_for_empty_input() -> None:
    assert sanitize_name_for_subdomain("---") == "unnamed"


def test_compute_subdomain_basic() -> None:
    result = compute_subdomain(
        service_name="web",
        agent_name="alice",
        host_name="dev-box",
    )
    assert result == "web.alice.dev-box"


def test_compute_subdomain_sanitizes_all_parts() -> None:
    result = compute_subdomain(
        service_name="Web_UI",
        agent_name="My_Agent",
        host_name="Dev.Box",
    )
    assert result == "web-ui.my-agent.dev-box"


def test_compute_service_url_default_suffix_and_port() -> None:
    url = compute_service_url(
        service_name="web",
        agent_name="alice",
        host_name="dev-box",
    )
    assert url == "http://web.alice.dev-box.mngr.localhost:8080"


def test_compute_service_url_custom_suffix_and_port() -> None:
    url = compute_service_url(
        service_name="api",
        agent_name="bob",
        host_name="staging",
        domain_suffix="example.com",
        vhost_port=9090,
    )
    assert url == "http://api.bob.staging.example.com:9090"


def test_build_forwarded_service_computes_all_fields() -> None:
    service = build_forwarded_service(
        service_name="terminal",
        local_port=7681,
        agent_name="alice",
        host_name="dev-box",
    )
    assert service.service_name == ForwardedServiceName("terminal")
    assert service.local_port == 7681
    assert service.agent_name == "alice"
    assert service.host_name == "dev-box"
    assert service.subdomain == "terminal.alice.dev-box"
    assert service.url == "http://terminal.alice.dev-box.mngr.localhost:8080"


def test_build_forwarded_service_with_custom_domain() -> None:
    service = build_forwarded_service(
        service_name="web",
        local_port=3000,
        agent_name="bob",
        host_name="prod",
        domain_suffix="my.domain",
        vhost_port=443,
    )
    assert service.url == "http://web.bob.prod.my.domain:443"
