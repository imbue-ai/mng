import pytest

from imbue.mng.config.data_types import MngContext
from imbue.mng.errors import UserInputError
from imbue.mng.primitives import AgentId
from imbue.mng.primitives import AgentName
from imbue.mng.primitives import DiscoveredAgent
from imbue.mng.primitives import DiscoveredHost
from imbue.mng.primitives import HostId
from imbue.mng.primitives import HostName
from imbue.mng.primitives import ProviderInstanceName
from imbue.mng_wait.api import _resolve_by_name
from imbue.mng_wait.primitives import WaitTargetType


def _make_agents_by_host(
    agent_name: str = "test-agent",
    host_name: str = "test-host",
) -> tuple[dict[DiscoveredHost, list[DiscoveredAgent]], DiscoveredHost, DiscoveredAgent]:
    host_id = HostId.generate()
    agent_id = AgentId.generate()
    host_ref = DiscoveredHost(
        host_id=host_id,
        host_name=HostName(host_name),
        provider_name=ProviderInstanceName("local"),
    )
    agent_ref = DiscoveredAgent(
        host_id=host_id,
        agent_id=agent_id,
        agent_name=AgentName(agent_name),
        provider_name=ProviderInstanceName("local"),
    )
    agents_by_host: dict[DiscoveredHost, list[DiscoveredAgent]] = {host_ref: [agent_ref]}
    return agents_by_host, host_ref, agent_ref


def test_resolve_by_name_finds_agent(temp_mng_ctx: MngContext) -> None:
    agents_by_host, host_ref, agent_ref = _make_agents_by_host(agent_name="my-agent")
    result = _resolve_by_name("my-agent", agents_by_host, temp_mng_ctx)
    assert result.target.target_type == WaitTargetType.AGENT
    assert result.agent_id == agent_ref.agent_id
    assert result.host_id == host_ref.host_id


def test_resolve_by_name_finds_host(temp_mng_ctx: MngContext) -> None:
    # Use a different host name than agent name to avoid ambiguity
    agents_by_host, host_ref, _agent_ref = _make_agents_by_host(
        agent_name="my-agent",
        host_name="my-host",
    )
    result = _resolve_by_name("my-host", agents_by_host, temp_mng_ctx)
    assert result.target.target_type == WaitTargetType.HOST
    assert result.agent_id is None
    assert result.host_id == host_ref.host_id


def test_resolve_by_name_raises_when_ambiguous(temp_mng_ctx: MngContext) -> None:
    # Create a scenario where the name matches both agent and host
    host_id = HostId.generate()
    shared_name = "ambiguous"
    host_ref = DiscoveredHost(
        host_id=host_id,
        host_name=HostName(shared_name),
        provider_name=ProviderInstanceName("local"),
    )
    agent_ref = DiscoveredAgent(
        host_id=host_id,
        agent_id=AgentId.generate(),
        agent_name=AgentName(shared_name),
        provider_name=ProviderInstanceName("local"),
    )
    agents_by_host: dict[DiscoveredHost, list[DiscoveredAgent]] = {host_ref: [agent_ref]}

    with pytest.raises(UserInputError, match="matches both"):
        _resolve_by_name(shared_name, agents_by_host, temp_mng_ctx)


def test_resolve_by_name_raises_when_not_found(temp_mng_ctx: MngContext) -> None:
    agents_by_host, _host_ref, _agent_ref = _make_agents_by_host()

    with pytest.raises(UserInputError, match="No agent or host found"):
        _resolve_by_name("nonexistent", agents_by_host, temp_mng_ctx)


def test_resolve_by_name_raises_when_multiple_agents(temp_mng_ctx: MngContext) -> None:
    # Two agents with same name on different hosts
    host_ref_1 = DiscoveredHost(
        host_id=HostId.generate(),
        host_name=HostName("host-1"),
        provider_name=ProviderInstanceName("local"),
    )
    host_ref_2 = DiscoveredHost(
        host_id=HostId.generate(),
        host_name=HostName("host-2"),
        provider_name=ProviderInstanceName("local"),
    )
    agent_ref_1 = DiscoveredAgent(
        host_id=host_ref_1.host_id,
        agent_id=AgentId.generate(),
        agent_name=AgentName("dup-agent"),
        provider_name=ProviderInstanceName("local"),
    )
    agent_ref_2 = DiscoveredAgent(
        host_id=host_ref_2.host_id,
        agent_id=AgentId.generate(),
        agent_name=AgentName("dup-agent"),
        provider_name=ProviderInstanceName("local"),
    )
    agents_by_host: dict[DiscoveredHost, list[DiscoveredAgent]] = {
        host_ref_1: [agent_ref_1],
        host_ref_2: [agent_ref_2],
    }

    with pytest.raises(UserInputError, match="Multiple agents"):
        _resolve_by_name("dup-agent", agents_by_host, temp_mng_ctx)


def test_resolve_by_name_raises_when_multiple_hosts(temp_mng_ctx: MngContext) -> None:
    # Two hosts with the same name
    host_ref_1 = DiscoveredHost(
        host_id=HostId.generate(),
        host_name=HostName("dup-host"),
        provider_name=ProviderInstanceName("local"),
    )
    host_ref_2 = DiscoveredHost(
        host_id=HostId.generate(),
        host_name=HostName("dup-host"),
        provider_name=ProviderInstanceName("local"),
    )
    agents_by_host: dict[DiscoveredHost, list[DiscoveredAgent]] = {
        host_ref_1: [],
        host_ref_2: [],
    }

    with pytest.raises(UserInputError, match="Multiple hosts"):
        _resolve_by_name("dup-host", agents_by_host, temp_mng_ctx)
