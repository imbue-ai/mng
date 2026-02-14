"""Acceptance tests for the mngr serve command.

Starts the API server as a real subprocess and makes HTTP requests against it.
These tests verify the full end-to-end behavior including CLI argument parsing,
token generation, server startup, and HTTP request handling.
"""

import signal
import subprocess
from contextlib import contextmanager
from pathlib import Path
from typing import Generator
from typing import NamedTuple

import httpx
import pytest

from imbue.mngr.plugins.api_server.auth import read_or_create_api_token
from imbue.mngr.utils.polling import wait_for
from imbue.mngr.utils.testing import find_free_port
from imbue.mngr.utils.testing import get_subprocess_test_env
from imbue.mngr.utils.testing import is_port_open


class _RunningServeProcess(NamedTuple):
    """State for a running mngr serve subprocess."""

    port: int
    config_dir: Path
    base_url: str


@contextmanager
def _serve_subprocess(
    tmp_path: Path,
    root_name: str = "mngr-serve-acceptance",
    startup_timeout: float = 15.0,
) -> Generator[_RunningServeProcess, None, None]:
    """Start mngr serve, wait for it to accept connections, and tear it down on exit."""
    port = find_free_port()
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    host_dir = tmp_path / ".mngr"
    host_dir.mkdir(exist_ok=True)

    env = get_subprocess_test_env(root_name=root_name, host_dir=host_dir)

    proc = subprocess.Popen(
        [
            "uv",
            "run",
            "mngr",
            "serve",
            "--port",
            str(port),
            "--host",
            "127.0.0.1",
            "--config-dir",
            str(config_dir),
        ],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        wait_for(
            lambda: is_port_open(port),
            timeout=startup_timeout,
            error_message=f"mngr serve did not start within timeout on port {port}",
        )
        yield _RunningServeProcess(port=port, config_dir=config_dir, base_url=f"http://127.0.0.1:{port}")
    finally:
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


@pytest.mark.acceptance
@pytest.mark.timeout(60)
def test_serve_starts_and_responds(tmp_path: Path) -> None:
    """mngr serve starts a server that responds to HTTP requests."""
    with _serve_subprocess(tmp_path) as server:
        response = httpx.get(f"{server.base_url}/", timeout=5.0)
        assert response.status_code == 200
        assert "<!DOCTYPE html>" in response.text
        assert "mngr" in response.text.lower()


@pytest.mark.acceptance
@pytest.mark.timeout(60)
def test_serve_authenticates_with_generated_token(tmp_path: Path) -> None:
    """mngr serve generates a token that can be used to authenticate API requests."""
    with _serve_subprocess(tmp_path) as server:
        token = read_or_create_api_token(server.config_dir)
        headers = {"Authorization": f"Bearer {token.get_secret_value()}"}

        # Authenticated request should succeed
        response = httpx.get(f"{server.base_url}/api/agents", headers=headers, timeout=5.0)
        assert response.status_code == 200
        data = response.json()
        assert "agents" in data
        assert isinstance(data["agents"], list)

        # Unauthenticated request should fail
        response = httpx.get(f"{server.base_url}/api/agents", timeout=5.0)
        assert response.status_code == 401

        # Wrong token should fail
        response = httpx.get(
            f"{server.base_url}/api/agents",
            headers={"Authorization": "Bearer wrong-token"},
            timeout=5.0,
        )
        assert response.status_code == 401


@pytest.mark.acceptance
@pytest.mark.timeout(60)
def test_serve_no_sse_endpoint(tmp_path: Path) -> None:
    """The SSE streaming endpoint should not exist (replaced by polling)."""
    with _serve_subprocess(tmp_path) as server:
        token = read_or_create_api_token(server.config_dir)
        headers = {"Authorization": f"Bearer {token.get_secret_value()}"}

        response = httpx.get(
            f"{server.base_url}/api/agents/stream",
            headers=headers,
            params={"token": token.get_secret_value()},
            timeout=5.0,
        )
        assert response.status_code in (404, 405, 422)
