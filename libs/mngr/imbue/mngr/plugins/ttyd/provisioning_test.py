"""Unit tests for ttyd provisioning functions."""

from pathlib import Path

from imbue.mngr.conftest import create_test_base_agent
from imbue.mngr.plugins.ttyd.provisioning import _compute_agent_state_dir
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
