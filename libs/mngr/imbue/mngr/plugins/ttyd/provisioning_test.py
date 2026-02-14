"""Unit tests for ttyd provisioning functions."""

from pathlib import Path

from imbue.mngr.conftest import create_test_base_agent
from imbue.mngr.plugins.ttyd.provisioning import _compute_agent_state_dir
from imbue.mngr.plugins.ttyd.provisioning import _write_local_terminal_url
from imbue.mngr.providers.local.instance import LocalProviderInstance


def test_compute_agent_state_dir(
    local_provider: LocalProviderInstance,
    temp_host_dir: Path,
    temp_work_dir: Path,
) -> None:
    """Test that _compute_agent_state_dir returns the correct path."""
    agent = create_test_base_agent(local_provider, temp_host_dir, temp_work_dir)
    host = agent.get_host()

    state_dir = _compute_agent_state_dir(host, agent.id)

    assert state_dir == host.host_dir / "agents" / str(agent.id)


def test_write_local_terminal_url_creates_url_file(
    local_provider: LocalProviderInstance,
    temp_host_dir: Path,
    temp_work_dir: Path,
) -> None:
    """Test that _write_local_terminal_url writes the URL to status/urls/terminal."""
    agent = create_test_base_agent(local_provider, temp_host_dir, temp_work_dir)
    host = agent.get_host()
    agent_state_dir = _compute_agent_state_dir(host, agent.id)

    _write_local_terminal_url(host, agent_state_dir, ttyd_port=7681)

    url_file = agent_state_dir / "status" / "urls" / "terminal"
    assert url_file.exists()
    assert url_file.read_text() == "http://localhost:7681"


def test_write_local_terminal_url_is_picked_up_by_get_reported_urls(
    local_provider: LocalProviderInstance,
    temp_host_dir: Path,
    temp_work_dir: Path,
) -> None:
    """Test the full chain: write URL file -> get_reported_urls() returns it."""
    agent = create_test_base_agent(local_provider, temp_host_dir, temp_work_dir)
    host = agent.get_host()
    agent_state_dir = _compute_agent_state_dir(host, agent.id)

    _write_local_terminal_url(host, agent_state_dir, ttyd_port=7700)

    urls = agent.get_reported_urls()
    assert "terminal" in urls
    assert urls["terminal"] == "http://localhost:7700"
