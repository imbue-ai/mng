"""Integration tests for the forward-service shell script.

These tests generate the forward-service script, install it into a temp
directory, and run it with real bash to verify end-to-end behavior.
"""

import os
import stat
import subprocess
from pathlib import Path

import pytest

from imbue.mngr.plugins.port_forwarding.forward_service_script import generate_forward_service_script


@pytest.fixture()
def forward_service_env(tmp_path: Path) -> dict[str, str]:
    """Set up a temp directory structure simulating a remote host and return env vars."""
    agent_state_dir = tmp_path / "agents" / "agent-001"
    agent_state_dir.mkdir(parents=True)

    frpc_config_dir = tmp_path / "frpc"
    frpc_config_dir.mkdir(parents=True)

    # Install the generated script
    script_content = generate_forward_service_script(
        domain_suffix="mngr.localhost",
        vhost_port=8080,
        frpc_config_dir=str(frpc_config_dir),
    )
    script_path = tmp_path / "forward-service"
    script_path.write_text(script_content)
    script_path.chmod(script_path.stat().st_mode | stat.S_IEXEC)

    env = os.environ.copy()
    env["MNGR_AGENT_STATE_DIR"] = str(agent_state_dir)
    env["MNGR_AGENT_NAME"] = "alice"
    env["MNGR_HOST_NAME"] = "dev-box"
    return env


def _run_forward_service(
    tmp_path: Path,
    env: dict[str, str],
    args: list[str],
) -> subprocess.CompletedProcess[str]:
    script_path = tmp_path / "forward-service"
    return subprocess.run(
        ["bash", str(script_path), *args],
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
    )


def test_forward_service_add_writes_url_to_status_dir(
    tmp_path: Path,
    forward_service_env: dict[str, str],
) -> None:
    """Running 'add --name web --port 3000' should write the URL to status/urls/web."""
    result = _run_forward_service(tmp_path, forward_service_env, ["add", "--name", "web", "--port", "3000"])

    assert result.returncode == 0, f"stderr: {result.stderr}"
    expected_url = "http://web.alice.dev-box.mngr.localhost:8080"
    assert expected_url in result.stdout

    agent_state_dir = Path(forward_service_env["MNGR_AGENT_STATE_DIR"])
    url_file = agent_state_dir / "status" / "urls" / "web"
    assert url_file.exists()
    assert url_file.read_text() == expected_url


def test_forward_service_add_creates_frpc_proxy_config(
    tmp_path: Path,
    forward_service_env: dict[str, str],
) -> None:
    """Running 'add' should create a frpc proxy config fragment."""
    result = _run_forward_service(tmp_path, forward_service_env, ["add", "--name", "api", "--port", "8000"])

    assert result.returncode == 0, f"stderr: {result.stderr}"

    frpc_config_dir = tmp_path / "frpc"
    proxy_file = frpc_config_dir / "proxies" / "api-alice-dev-box.toml"
    assert proxy_file.exists()

    content = proxy_file.read_text()
    assert "[[proxies]]" in content
    assert 'name = "api-alice-dev-box"' in content
    assert 'type = "http"' in content
    assert "localPort = 8000" in content
    assert 'customDomains = ["api.alice.dev-box.mngr.localhost"]' in content


def test_forward_service_remove_cleans_up_url_and_proxy(
    tmp_path: Path,
    forward_service_env: dict[str, str],
) -> None:
    """Running 'remove' should delete both the URL file and the proxy config."""
    # First add a service
    _run_forward_service(tmp_path, forward_service_env, ["add", "--name", "web", "--port", "3000"])

    agent_state_dir = Path(forward_service_env["MNGR_AGENT_STATE_DIR"])
    url_file = agent_state_dir / "status" / "urls" / "web"
    proxy_file = tmp_path / "frpc" / "proxies" / "web-alice-dev-box.toml"
    assert url_file.exists()
    assert proxy_file.exists()

    # Now remove it
    result = _run_forward_service(tmp_path, forward_service_env, ["remove", "--name", "web"])
    assert result.returncode == 0, f"stderr: {result.stderr}"

    assert not url_file.exists()
    assert not proxy_file.exists()


def test_forward_service_list_shows_forwarded_services(
    tmp_path: Path,
    forward_service_env: dict[str, str],
) -> None:
    """Running 'list' should show all forwarded services."""
    _run_forward_service(tmp_path, forward_service_env, ["add", "--name", "web", "--port", "3000"])
    _run_forward_service(tmp_path, forward_service_env, ["add", "--name", "api", "--port", "8000"])

    result = _run_forward_service(tmp_path, forward_service_env, ["list"])
    assert result.returncode == 0, f"stderr: {result.stderr}"

    assert "web" in result.stdout
    assert "api" in result.stdout
    assert "mngr.localhost" in result.stdout


def test_forward_service_list_empty_shows_no_services(
    tmp_path: Path,
    forward_service_env: dict[str, str],
) -> None:
    """Running 'list' with no services should indicate none are forwarded."""
    result = _run_forward_service(tmp_path, forward_service_env, ["list"])
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "No forwarded services" in result.stdout


def test_forward_service_add_sanitizes_names(
    tmp_path: Path,
    forward_service_env: dict[str, str],
) -> None:
    """Names with uppercase, underscores, and dots should be sanitized."""
    forward_service_env["MNGR_AGENT_NAME"] = "My_Agent"
    forward_service_env["MNGR_HOST_NAME"] = "Dev.Box"

    result = _run_forward_service(tmp_path, forward_service_env, ["add", "--name", "Web_UI", "--port", "3000"])
    assert result.returncode == 0, f"stderr: {result.stderr}"

    # The URL should use sanitized names
    assert "web-ui.my-agent.dev-box.mngr.localhost:8080" in result.stdout


def test_forward_service_add_missing_name_fails(
    tmp_path: Path,
    forward_service_env: dict[str, str],
) -> None:
    """Missing --name should cause a non-zero exit."""
    result = _run_forward_service(tmp_path, forward_service_env, ["add", "--port", "3000"])
    assert result.returncode != 0


def test_forward_service_add_missing_port_fails(
    tmp_path: Path,
    forward_service_env: dict[str, str],
) -> None:
    """Missing --port should cause a non-zero exit."""
    result = _run_forward_service(tmp_path, forward_service_env, ["add", "--name", "web"])
    assert result.returncode != 0


def test_forward_service_add_missing_env_var_fails(
    tmp_path: Path,
    forward_service_env: dict[str, str],
) -> None:
    """Missing MNGR_AGENT_STATE_DIR should cause a non-zero exit."""
    del forward_service_env["MNGR_AGENT_STATE_DIR"]
    result = _run_forward_service(tmp_path, forward_service_env, ["add", "--name", "web", "--port", "3000"])
    assert result.returncode != 0


def test_forward_service_no_args_shows_usage(
    tmp_path: Path,
    forward_service_env: dict[str, str],
) -> None:
    """Running with no arguments should show usage and exit non-zero."""
    result = _run_forward_service(tmp_path, forward_service_env, [])
    assert result.returncode != 0
    assert "Usage" in result.stderr or "Usage" in result.stdout
