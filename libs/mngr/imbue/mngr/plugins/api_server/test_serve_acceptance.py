"""Acceptance tests for the mngr serve command.

Starts the API server as a real subprocess and makes HTTP requests against it.
These tests verify the full end-to-end behavior including CLI argument parsing,
token generation, server startup, and HTTP request handling.
"""

import signal
import subprocess
from pathlib import Path

import httpx
import pytest

from imbue.mngr.plugins.api_server.auth import read_or_create_api_token
from imbue.mngr.utils.polling import wait_for
from imbue.mngr.utils.testing import find_free_port
from imbue.mngr.utils.testing import get_subprocess_test_env
from imbue.mngr.utils.testing import is_port_open


def _start_serve_subprocess(
    port: int,
    env: dict[str, str],
    config_dir: Path,
) -> subprocess.Popen[str]:
    """Start mngr serve as a subprocess on the given port."""
    return subprocess.Popen(
        [
            "uv", "run", "mngr",
            "--disable-plugin", "modal",
            "serve",
            "--port", str(port),
            "--host", "127.0.0.1",
            "--config-dir", str(config_dir),
        ],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


@pytest.mark.acceptance
@pytest.mark.timeout(60)
def test_serve_starts_and_responds(tmp_path: Path) -> None:
    """mngr serve starts a server that responds to HTTP requests."""
    port = find_free_port()
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    host_dir = tmp_path / ".mngr"
    host_dir.mkdir()

    env = get_subprocess_test_env(
        root_name="mngr-serve-acceptance",
        host_dir=host_dir,
    )

    proc = _start_serve_subprocess(port, env, config_dir)
    try:
        wait_for(
            lambda: is_port_open(port),
            timeout=15.0,
            error_message=f"mngr serve did not start within timeout on port {port}",
        )

        # The server is up -- the root endpoint should return the web UI
        response = httpx.get(f"http://127.0.0.1:{port}/", timeout=5.0)
        assert response.status_code == 200
        assert "<!DOCTYPE html>" in response.text
        assert "mngr" in response.text.lower()
    finally:
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


@pytest.mark.acceptance
@pytest.mark.timeout(60)
def test_serve_authenticates_with_generated_token(tmp_path: Path) -> None:
    """mngr serve generates a token that can be used to authenticate API requests."""
    port = find_free_port()
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    host_dir = tmp_path / ".mngr"
    host_dir.mkdir()

    env = get_subprocess_test_env(
        root_name="mngr-serve-acceptance",
        host_dir=host_dir,
    )

    proc = _start_serve_subprocess(port, env, config_dir)
    try:
        wait_for(
            lambda: is_port_open(port),
            timeout=15.0,
            error_message=f"mngr serve did not start within timeout on port {port}",
        )

        # Read the token that the server generated
        token = read_or_create_api_token(config_dir)
        headers = {"Authorization": f"Bearer {token.get_secret_value()}"}

        # Authenticated request should succeed
        response = httpx.get(
            f"http://127.0.0.1:{port}/api/agents",
            headers=headers,
            timeout=5.0,
        )
        assert response.status_code == 200
        data = response.json()
        assert "agents" in data
        assert isinstance(data["agents"], list)

        # Unauthenticated request should fail
        response = httpx.get(
            f"http://127.0.0.1:{port}/api/agents",
            timeout=5.0,
        )
        assert response.status_code == 401

        # Wrong token should fail
        response = httpx.get(
            f"http://127.0.0.1:{port}/api/agents",
            headers={"Authorization": "Bearer wrong-token"},
            timeout=5.0,
        )
        assert response.status_code == 401
    finally:
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


@pytest.mark.acceptance
@pytest.mark.timeout(60)
def test_serve_no_sse_endpoint(tmp_path: Path) -> None:
    """The SSE streaming endpoint should not exist (replaced by polling)."""
    port = find_free_port()
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    host_dir = tmp_path / ".mngr"
    host_dir.mkdir()

    env = get_subprocess_test_env(
        root_name="mngr-serve-acceptance",
        host_dir=host_dir,
    )

    proc = _start_serve_subprocess(port, env, config_dir)
    try:
        wait_for(
            lambda: is_port_open(port),
            timeout=15.0,
            error_message=f"mngr serve did not start within timeout on port {port}",
        )

        token = read_or_create_api_token(config_dir)
        headers = {"Authorization": f"Bearer {token.get_secret_value()}"}

        # The SSE endpoint should not exist (404 or 405)
        response = httpx.get(
            f"http://127.0.0.1:{port}/api/agents/stream",
            headers=headers,
            params={"token": token.get_secret_value()},
            timeout=5.0,
        )
        assert response.status_code in (404, 405, 422)
    finally:
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
