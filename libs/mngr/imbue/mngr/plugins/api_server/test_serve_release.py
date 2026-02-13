"""Release tests for the mngr serve command.

These tests verify the API server works with the full provider stack,
including Modal. They require Modal credentials and run only on main.
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


@pytest.mark.release
@pytest.mark.timeout(120)
def test_serve_lists_agents_with_all_providers(tmp_path: Path) -> None:
    """mngr serve with all providers enabled returns a valid agent list.

    Unlike acceptance tests which use --disable-plugin modal, this test
    starts the server with the full provider stack (local + modal + ssh).
    """
    port = find_free_port()
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    host_dir = tmp_path / ".mngr"
    host_dir.mkdir()

    env = get_subprocess_test_env(
        root_name="mngr-serve-release",
        host_dir=host_dir,
    )

    # Start serve without --disable-plugin modal (all providers enabled)
    proc = subprocess.Popen(
        [
            "uv", "run", "mngr",
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

    try:
        wait_for(
            lambda: is_port_open(port),
            timeout=30.0,
            error_message=f"mngr serve (full stack) did not start within timeout on port {port}",
        )

        token = read_or_create_api_token(config_dir)
        headers = {"Authorization": f"Bearer {token.get_secret_value()}"}

        # List agents -- should succeed even with Modal provider loaded
        response = httpx.get(
            f"http://127.0.0.1:{port}/api/agents",
            headers=headers,
            timeout=10.0,
        )
        assert response.status_code == 200
        data = response.json()
        assert "agents" in data
        assert isinstance(data["agents"], list)

        # Verify errors field is present (may contain provider errors if not configured)
        assert "errors" in data
    finally:
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
