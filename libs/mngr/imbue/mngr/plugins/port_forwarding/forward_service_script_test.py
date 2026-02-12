"""Unit tests for the forward-service script generation."""

from imbue.mngr.plugins.port_forwarding.forward_service_script import generate_forward_service_script


def test_generate_forward_service_script_contains_shebang() -> None:
    script = generate_forward_service_script(
        domain_suffix="mngr.localhost",
        vhost_port=8080,
        frpc_config_dir="/etc/frpc",
    )
    assert script.startswith("#!/usr/bin/env bash")


def test_generate_forward_service_script_embeds_domain_suffix() -> None:
    script = generate_forward_service_script(
        domain_suffix="custom.domain",
        vhost_port=9090,
        frpc_config_dir="/etc/frpc",
    )
    assert 'DOMAIN_SUFFIX="custom.domain"' in script
    assert 'VHOST_PORT="9090"' in script


def test_generate_forward_service_script_embeds_frpc_config_dir() -> None:
    script = generate_forward_service_script(
        domain_suffix="mngr.localhost",
        vhost_port=8080,
        frpc_config_dir="/opt/frpc",
    )
    assert 'FRPC_CONFIG_DIR="/opt/frpc"' in script


def test_generate_forward_service_script_contains_add_command() -> None:
    script = generate_forward_service_script(
        domain_suffix="mngr.localhost",
        vhost_port=8080,
        frpc_config_dir="/etc/frpc",
    )
    assert "cmd_add" in script
    assert "--name" in script
    assert "--port" in script


def test_generate_forward_service_script_contains_remove_command() -> None:
    script = generate_forward_service_script(
        domain_suffix="mngr.localhost",
        vhost_port=8080,
        frpc_config_dir="/etc/frpc",
    )
    assert "cmd_remove" in script


def test_generate_forward_service_script_contains_list_command() -> None:
    script = generate_forward_service_script(
        domain_suffix="mngr.localhost",
        vhost_port=8080,
        frpc_config_dir="/etc/frpc",
    )
    assert "cmd_list" in script


def test_generate_forward_service_script_writes_to_status_urls() -> None:
    script = generate_forward_service_script(
        domain_suffix="mngr.localhost",
        vhost_port=8080,
        frpc_config_dir="/etc/frpc",
    )
    assert "status/urls" in script
    assert "MNGR_AGENT_STATE_DIR" in script
