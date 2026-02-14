"""Unit tests for the port forwarding plugin module."""

from pathlib import Path

from imbue.mngr.conftest import create_test_base_agent
from imbue.mngr.plugins.port_forwarding.plugin import _resolve_config_from_agent
from imbue.mngr.providers.local.instance import LocalProviderInstance


def test_resolve_config_from_agent_returns_none_when_not_configured(
    local_provider: LocalProviderInstance,
    temp_host_dir: Path,
    temp_work_dir: Path,
) -> None:
    """Test that _resolve_config_from_agent returns None when no plugin config exists."""
    agent = create_test_base_agent(local_provider, temp_host_dir, temp_work_dir)
    config = _resolve_config_from_agent(agent)
    assert config is None
