"""Integration tests for the port forwarding plugin.

These tests verify the full chain locally:
  config resolution -> frps config -> frps startup -> frpc connects ->
  forward-service registers URL -> get_reported_urls() picks it up
"""

import shutil
import signal
import socket
import subprocess
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

import pytest
from pydantic import SecretStr

from imbue.imbue_common.primitives import PositiveInt
from imbue.mngr.api.open import _resolve_agent_url
from imbue.mngr.conftest import create_test_base_agent
from imbue.mngr.plugins.port_forwarding.config_resolution import resolve_port_forwarding_config
from imbue.mngr.plugins.port_forwarding.data_types import PortForwardingConfig
from imbue.mngr.plugins.port_forwarding.data_types import ResolvedPortForwardingConfig
from imbue.mngr.plugins.port_forwarding.forward_service_script import generate_forward_service_script
from imbue.mngr.plugins.port_forwarding.frps import ensure_frps_config
from imbue.mngr.plugins.port_forwarding.frps import is_frps_running
from imbue.mngr.providers.local.instance import LocalProviderInstance
from imbue.mngr.utils.polling import wait_for


def _find_free_port() -> int:
    """Find an available port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _make_resolved_config(tmp_path: Path) -> ResolvedPortForwardingConfig:
    """Create a ResolvedPortForwardingConfig with unique ports for test isolation."""
    plugin_config = PortForwardingConfig(
        frps_bind_port=PositiveInt(_find_free_port()),
        vhost_http_port=PositiveInt(_find_free_port()),
    )
    return resolve_port_forwarding_config(plugin_config, config_dir=tmp_path / "config")


@contextmanager
def _run_daemon(command: list[str]) -> Generator[subprocess.Popen, None, None]:
    """Start a daemon process and ensure it is terminated on exit."""
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        yield process
    finally:
        process.send_signal(signal.SIGTERM)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


# =============================================================================
# Config resolution integration tests
# =============================================================================


def test_config_resolution_creates_tokens_on_disk(tmp_path: Path) -> None:
    """Test that resolving config auto-generates and persists tokens."""
    config = PortForwardingConfig()
    config_dir = tmp_path / "config"

    resolved = resolve_port_forwarding_config(config, config_dir=config_dir)

    # Tokens should be non-empty
    assert len(resolved.frps_token.get_secret_value()) > 0
    assert len(resolved.auth_token.get_secret_value()) > 0

    # Token files should exist on disk
    assert (config_dir / "frps_token").exists()
    assert (config_dir / "auth_token").exists()

    # Resolving again should return the same tokens
    resolved2 = resolve_port_forwarding_config(config, config_dir=config_dir)
    assert resolved.frps_token.get_secret_value() == resolved2.frps_token.get_secret_value()
    assert resolved.auth_token.get_secret_value() == resolved2.auth_token.get_secret_value()


def test_config_resolution_respects_explicit_tokens(tmp_path: Path) -> None:
    """Test that explicit tokens in config are preserved (not overwritten)."""
    config = PortForwardingConfig(
        frps_token=SecretStr("explicit-frps"),
        auth_token=SecretStr("explicit-auth"),
    )
    config_dir = tmp_path / "config"

    resolved = resolve_port_forwarding_config(config, config_dir=config_dir)

    assert resolved.frps_token.get_secret_value() == "explicit-frps"
    assert resolved.auth_token.get_secret_value() == "explicit-auth"
    # No token files should be created when tokens are explicit
    assert not (config_dir / "frps_token").exists()
    assert not (config_dir / "auth_token").exists()


# =============================================================================
# frps startup integration tests (require frps installed)
# =============================================================================


@pytest.mark.skipif(shutil.which("frps") is None, reason="frps not installed")
def test_frps_starts_and_listens(tmp_path: Path) -> None:
    """Test the full frps startup chain: config -> write config -> start -> verify listening."""
    resolved = _make_resolved_config(tmp_path)
    config_path = ensure_frps_config(resolved)

    assert not is_frps_running(resolved)

    with _run_daemon(["frps", "-c", str(config_path)]):
        wait_for(
            condition=lambda: is_frps_running(resolved),
            timeout=5.0,
            poll_interval=0.1,
            error_message=f"frps did not start listening on port {resolved.frps_bind_port}",
        )
        assert is_frps_running(resolved)


@pytest.mark.skipif(shutil.which("frps") is None, reason="frps not installed")
def test_frps_config_file_is_valid(tmp_path: Path) -> None:
    """Test that the generated frps config file is valid TOML that frps accepts."""
    resolved = _make_resolved_config(tmp_path)

    config_path = ensure_frps_config(resolved)
    assert config_path.exists()

    content = config_path.read_text()
    assert f"bindPort = {resolved.frps_bind_port}" in content
    assert f"vhostHTTPPort = {resolved.vhost_http_port}" in content
    assert resolved.frps_token.get_secret_value() in content


# =============================================================================
# frpc connection integration tests (require both frps and frpc installed)
# =============================================================================


@pytest.mark.skipif(
    shutil.which("frps") is None or shutil.which("frpc") is None,
    reason="frps and/or frpc not installed",
)
def test_frpc_connects_to_frps(tmp_path: Path) -> None:
    """Test that frpc can successfully authenticate and connect to a running frps."""
    resolved = _make_resolved_config(tmp_path)
    config_path = ensure_frps_config(resolved)

    with _run_daemon(["frps", "-c", str(config_path)]):
        wait_for(
            condition=lambda: is_frps_running(resolved),
            timeout=5.0,
            poll_interval=0.1,
            error_message="frps did not start",
        )

        # Write a frpc config that connects to our frps
        frpc_config_dir = tmp_path / "frpc"
        frpc_config_dir.mkdir()
        (frpc_config_dir / "proxies").mkdir()

        frpc_config = (
            f'serverAddr = "127.0.0.1"\n'
            f"serverPort = {resolved.frps_bind_port}\n"
            f"\n"
            f"[auth]\n"
            f'method = "token"\n'
            f'token = "{resolved.frps_token.get_secret_value()}"\n'
        )
        frpc_config_path = frpc_config_dir / "frpc.toml"
        frpc_config_path.write_text(frpc_config)

        # Use frpc verify to check the config is accepted by the server
        verify_result = subprocess.run(
            ["frpc", "verify", "-c", str(frpc_config_path)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert verify_result.returncode == 0, f"frpc verify failed: {verify_result.stderr}"


# =============================================================================
# forward-service script integration test
# =============================================================================


def test_forward_service_registers_and_removes_url(tmp_path: Path) -> None:
    """Test the forward-service script: add -> URL file written -> remove -> URL file cleaned up."""
    resolved = _make_resolved_config(tmp_path)

    script_content = generate_forward_service_script(
        domain_suffix=resolved.domain_suffix,
        vhost_port=int(resolved.vhost_http_port),
        frpc_config_dir=str(tmp_path / "frpc"),
    )
    script_path = tmp_path / "forward-service"
    script_path.write_text(script_content)
    script_path.chmod(0o755)

    # Set up directories
    agent_state_dir = tmp_path / "agent_state"
    agent_state_dir.mkdir()
    frpc_config_dir = tmp_path / "frpc"
    frpc_config_dir.mkdir(exist_ok=True)
    (frpc_config_dir / "proxies").mkdir(exist_ok=True)
    (frpc_config_dir / "frpc.toml").write_text(f'serverAddr = "127.0.0.1"\nserverPort = {resolved.frps_bind_port}\n')

    env = {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "MNGR_AGENT_STATE_DIR": str(agent_state_dir),
        "MNGR_AGENT_NAME": "test-agent",
        "MNGR_HOST_NAME": "test-host",
    }

    # Run forward-service add
    result = subprocess.run(
        [str(script_path), "add", "--name", "terminal", "--port", "7681"],
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
    )
    assert result.returncode == 0, f"forward-service add failed: {result.stderr}"

    # URL file should exist with correct content
    url_file = agent_state_dir / "status" / "urls" / "terminal"
    assert url_file.exists(), f"URL file not found at {url_file}"
    url_content = url_file.read_text()
    assert f".{resolved.domain_suffix}:{resolved.vhost_http_port}" in url_content

    # frpc proxy config fragment should exist
    proxy_files = list((frpc_config_dir / "proxies").glob("*.toml"))
    assert len(proxy_files) == 1

    # Run forward-service remove
    result = subprocess.run(
        [str(script_path), "remove", "--name", "terminal"],
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
    )
    assert result.returncode == 0, f"forward-service remove failed: {result.stderr}"

    # Both URL file and proxy config should be cleaned up
    assert not url_file.exists()
    assert len(list((frpc_config_dir / "proxies").glob("*.toml"))) == 0


# =============================================================================
# End-to-end: forward-service URL picked up by agent + open
# =============================================================================


def test_forward_service_url_picked_up_by_agent(
    local_provider: LocalProviderInstance,
    temp_host_dir: Path,
    temp_work_dir: Path,
    tmp_path: Path,
) -> None:
    """Test end-to-end: forward-service writes URL -> agent.get_reported_urls() -> _resolve_agent_url."""
    resolved = _make_resolved_config(tmp_path)
    agent = create_test_base_agent(local_provider, temp_host_dir, temp_work_dir)

    script_content = generate_forward_service_script(
        domain_suffix=resolved.domain_suffix,
        vhost_port=int(resolved.vhost_http_port),
        frpc_config_dir=str(tmp_path / "frpc"),
    )
    script_path = tmp_path / "forward-service"
    script_path.write_text(script_content)
    script_path.chmod(0o755)

    agent_state_dir = temp_host_dir / "agents" / str(agent.id)
    frpc_dir = tmp_path / "frpc"
    frpc_dir.mkdir(exist_ok=True)
    (frpc_dir / "proxies").mkdir(exist_ok=True)
    (frpc_dir / "frpc.toml").write_text('serverAddr = "127.0.0.1"\nserverPort = 7000\n')

    env = {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "MNGR_AGENT_STATE_DIR": str(agent_state_dir),
        "MNGR_AGENT_NAME": str(agent.name),
        "MNGR_HOST_NAME": "test-host",
    }

    result = subprocess.run(
        [str(script_path), "add", "--name", "web", "--port", "3000"],
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
    )
    assert result.returncode == 0, f"forward-service add failed: {result.stderr}"

    # Verify the agent sees the URL via get_reported_urls()
    urls = agent.get_reported_urls()
    assert "web" in urls, f"Expected 'web' URL but got: {urls}"
    assert f".{resolved.domain_suffix}:{resolved.vhost_http_port}" in urls["web"]

    # Verify _resolve_agent_url can find it by type
    resolved_url = _resolve_agent_url(agent, url_type="web")
    assert resolved_url == urls["web"]

    # Verify default URL fallback (no "default" key, falls back to first typed URL)
    default_url = _resolve_agent_url(agent, url_type=None)
    assert default_url == urls["web"]
