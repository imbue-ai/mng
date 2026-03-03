"""Test fixtures for mng-changeling-chat.

Uses shared plugin test fixtures from mng for common setup (plugin manager,
environment isolation, git repos, etc.) and defines chat-specific fixtures below.
"""

from datetime import datetime
from datetime import timezone
from pathlib import Path
from uuid import uuid4

import pytest

from imbue.mng.agents.base_agent import BaseAgent
from imbue.mng.config.data_types import AgentTypeConfig
from imbue.mng.config.data_types import MngContext
from imbue.mng.hosts.host import Host
from imbue.mng.interfaces.data_types import PyinfraConnector
from imbue.mng.primitives import AgentId
from imbue.mng.primitives import AgentName
from imbue.mng.primitives import AgentTypeName
from imbue.mng.primitives import HostId
from imbue.mng.providers.local.instance import LocalProviderInstance
from imbue.mng.utils.plugin_testing import register_plugin_test_fixtures

register_plugin_test_fixtures(globals())


class _TestAgent(BaseAgent):
    """Test agent that avoids SSH access for get_expected_process_name."""

    def get_expected_process_name(self) -> str:
        return "test-process"


@pytest.fixture
def local_host_and_agent(
    local_provider: LocalProviderInstance,
    temp_mng_ctx: MngContext,
) -> tuple[Host, _TestAgent]:
    """Create a local host and test agent for chat plugin tests."""
    host = Host(
        id=HostId(f"host-{uuid4().hex}"),
        connector=PyinfraConnector(local_provider._create_local_pyinfra_host()),
        provider_instance=local_provider,
        mng_ctx=temp_mng_ctx,
    )
    agent = _TestAgent(
        id=AgentId(f"agent-{uuid4().hex}"),
        name=AgentName("test-agent"),
        agent_type=AgentTypeName("test"),
        work_dir=Path("/tmp/work"),
        create_time=datetime.now(timezone.utc),
        host_id=host.id,
        mng_ctx=temp_mng_ctx,
        agent_config=AgentTypeConfig(),
        host=host,
    )
    return host, agent
