"""Release tests for the mngr serve command.

These tests verify the API server works with the full provider stack,
including Modal. They require Modal credentials and run only on main.
"""

from pathlib import Path

import httpx
import pytest

from imbue.mngr.plugins.api_server.auth import read_or_create_api_token
from imbue.mngr.plugins.api_server.test_serve_acceptance import _serve_subprocess


@pytest.mark.release
@pytest.mark.timeout(120)
def test_serve_lists_agents_with_all_providers(tmp_path: Path) -> None:
    """mngr serve with all providers enabled returns a valid agent list.

    This release test uses a longer startup timeout to account for provider
    initialization. It verifies that the API server handles all providers
    gracefully, returning errors for any that fail to authenticate.
    """
    with _serve_subprocess(tmp_path, root_name="mngr-serve-release", startup_timeout=30.0) as server:
        token = read_or_create_api_token(server.config_dir)
        headers = {"Authorization": f"Bearer {token.get_secret_value()}"}

        # List agents -- should succeed even with Modal provider loaded
        response = httpx.get(f"{server.base_url}/api/agents", headers=headers, timeout=10.0)
        assert response.status_code == 200
        data = response.json()
        assert "agents" in data
        assert isinstance(data["agents"], list)

        # Verify errors field is present (may contain provider errors if not configured)
        assert "errors" in data
