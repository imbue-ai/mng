"""Unit tests for mngr remote provider instance."""

from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from pydantic import SecretStr

from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.errors import HostNotFoundError
from imbue.mngr.errors import ProviderError
from imbue.mngr.primitives import AgentId
from imbue.mngr.primitives import HostId
from imbue.mngr.primitives import HostName
from imbue.mngr.primitives import HostState
from imbue.mngr.primitives import ProviderInstanceName
from imbue.mngr.providers.mngr_remote.client import MngrRemoteClient
from imbue.mngr.providers.mngr_remote.instance import MngrRemoteProviderInstance
from imbue.mngr.providers.mngr_remote.remote_host import RemoteHost


def _make_agent_data(
    agent_id: str | None = None,
    agent_name: str | None = None,
    host_id: str | None = None,
    host_name: str = "test-host",
    host_state: str = "RUNNING",
) -> dict[str, Any]:
    """Build a fake agent dict matching the API server response shape."""
    return {
        "id": agent_id or str(AgentId()),
        "name": agent_name or f"agent-{uuid4().hex[:8]}",
        "type": "claude",
        "command": "claude --model opus",
        "work_dir": "/home/user/project",
        "create_time": "2025-01-01T00:00:00Z",
        "start_on_boot": True,
        "state": "RUNNING",
        "host": {
            "id": host_id or str(HostId()),
            "name": host_name,
            "provider_name": "modal",
            "state": host_state,
            "tags": {"env": "prod"},
            "image": "ubuntu:22.04",
        },
    }


class FakeClient(MngrRemoteClient):
    """Test double for MngrRemoteClient that returns canned data."""

    fake_agents: list[dict[str, Any]] = []
    should_raise: bool = False

    def list_agents(self) -> list[dict[str, Any]]:
        if self.should_raise:
            raise ProviderError("Connection refused")
        return list(self.fake_agents)


def _make_provider(
    temp_mngr_ctx: MngrContext,
    fake_agents: list[dict[str, Any]] | None = None,
    should_raise: bool = False,
) -> tuple[MngrRemoteProviderInstance, FakeClient]:
    """Create a provider instance with a fake client."""
    client = FakeClient(
        base_url="https://remote.example.com",
        token=SecretStr("test-token"),
        fake_agents=fake_agents or [],
        should_raise=should_raise,
    )
    provider = MngrRemoteProviderInstance(
        name=ProviderInstanceName("test-remote"),
        host_dir=Path("/tmp/mngr-remote"),
        mngr_ctx=temp_mngr_ctx,
        remote_url="https://remote.example.com",
        remote_token=SecretStr("test-token"),
    )
    # Monkey-patch _get_client to return our fake
    provider._get_client = lambda: client  # type: ignore[assignment]
    return provider, client


class TestListHosts:
    def test_returns_remote_hosts_grouped_by_host(self, temp_mngr_ctx: MngrContext) -> None:
        host_id = str(HostId())
        agents = [
            _make_agent_data(host_id=host_id, host_name="my-host", agent_name="agent-1"),
            _make_agent_data(host_id=host_id, host_name="my-host", agent_name="agent-2"),
        ]
        provider, _ = _make_provider(temp_mngr_ctx, fake_agents=agents)

        hosts = provider.list_hosts(cg=temp_mngr_ctx.concurrency_group)

        assert len(hosts) == 1
        host = hosts[0]
        assert isinstance(host, RemoteHost)
        assert str(host.id) == host_id
        assert host.get_name() == HostName("my-host")

    def test_returns_multiple_hosts(self, temp_mngr_ctx: MngrContext) -> None:
        host_id_1 = str(HostId())
        host_id_2 = str(HostId())
        agents = [
            _make_agent_data(host_id=host_id_1, host_name="host-a"),
            _make_agent_data(host_id=host_id_2, host_name="host-b"),
        ]
        provider, _ = _make_provider(temp_mngr_ctx, fake_agents=agents)

        hosts = provider.list_hosts(cg=temp_mngr_ctx.concurrency_group)

        assert len(hosts) == 2
        host_ids = {str(h.id) for h in hosts}
        assert host_ids == {host_id_1, host_id_2}

    def test_returns_empty_list_when_no_agents(self, temp_mngr_ctx: MngrContext) -> None:
        provider, _ = _make_provider(temp_mngr_ctx, fake_agents=[])

        hosts = provider.list_hosts(cg=temp_mngr_ctx.concurrency_group)

        assert hosts == []

    def test_raises_provider_error_when_api_unreachable(self, temp_mngr_ctx: MngrContext) -> None:
        provider, _ = _make_provider(temp_mngr_ctx, should_raise=True)

        with pytest.raises(ProviderError, match="Connection refused"):
            provider.list_hosts(cg=temp_mngr_ctx.concurrency_group)

    def test_skips_agents_without_host_id(self, temp_mngr_ctx: MngrContext) -> None:
        agents = [
            {"id": str(AgentId()), "name": "orphan", "host": {}},
            _make_agent_data(host_name="real-host"),
        ]
        provider, _ = _make_provider(temp_mngr_ctx, fake_agents=agents)

        hosts = provider.list_hosts(cg=temp_mngr_ctx.concurrency_group)

        assert len(hosts) == 1
        assert hosts[0].get_name() == HostName("real-host")


class TestRemoteHostState:
    def test_passes_through_running_state(self, temp_mngr_ctx: MngrContext) -> None:
        agents = [_make_agent_data(host_state="RUNNING")]
        provider, _ = _make_provider(temp_mngr_ctx, fake_agents=agents)

        hosts = provider.list_hosts(cg=temp_mngr_ctx.concurrency_group)

        assert hosts[0].get_state() == HostState.RUNNING

    def test_passes_through_stopped_state(self, temp_mngr_ctx: MngrContext) -> None:
        agents = [_make_agent_data(host_state="STOPPED")]
        provider, _ = _make_provider(temp_mngr_ctx, fake_agents=agents)

        hosts = provider.list_hosts(cg=temp_mngr_ctx.concurrency_group)

        assert hosts[0].get_state() == HostState.STOPPED

    def test_passes_through_paused_state(self, temp_mngr_ctx: MngrContext) -> None:
        agents = [_make_agent_data(host_state="PAUSED")]
        provider, _ = _make_provider(temp_mngr_ctx, fake_agents=agents)

        hosts = provider.list_hosts(cg=temp_mngr_ctx.concurrency_group)

        assert hosts[0].get_state() == HostState.PAUSED


class TestRemoteHostAgentReferences:
    def test_returns_agent_references_from_prefetched_data(self, temp_mngr_ctx: MngrContext) -> None:
        host_id = str(HostId())
        agent_id = str(AgentId())
        agents = [_make_agent_data(host_id=host_id, agent_id=agent_id, agent_name="my-agent")]
        provider, _ = _make_provider(temp_mngr_ctx, fake_agents=agents)

        hosts = provider.list_hosts(cg=temp_mngr_ctx.concurrency_group)
        refs = hosts[0].get_agent_references()

        assert len(refs) == 1
        assert str(refs[0].agent_id) == agent_id
        assert str(refs[0].agent_name) == "my-agent"

    def test_returns_multiple_agent_references(self, temp_mngr_ctx: MngrContext) -> None:
        host_id = str(HostId())
        agent_1 = _make_agent_data(host_id=host_id, agent_name="agent-1")
        agent_2 = _make_agent_data(host_id=host_id, agent_name="agent-2")
        provider, _ = _make_provider(temp_mngr_ctx, fake_agents=[agent_1, agent_2])

        hosts = provider.list_hosts(cg=temp_mngr_ctx.concurrency_group)
        refs = hosts[0].get_agent_references()

        assert len(refs) == 2
        names = {str(r.agent_name) for r in refs}
        assert names == {"agent-1", "agent-2"}

    def test_skips_malformed_agent_records(self, temp_mngr_ctx: MngrContext) -> None:
        host_id = str(HostId())
        agents = [
            _make_agent_data(host_id=host_id, agent_name="good-agent"),
            {
                "host": {"id": host_id, "name": "h", "provider_name": "modal", "state": "RUNNING"},
                # Missing 'id' field -- should be skipped
                "name": "bad-agent",
            },
        ]
        provider, _ = _make_provider(temp_mngr_ctx, fake_agents=agents)

        hosts = provider.list_hosts(cg=temp_mngr_ctx.concurrency_group)
        refs = hosts[0].get_agent_references()

        assert len(refs) == 1
        assert str(refs[0].agent_name) == "good-agent"


class TestGetHost:
    def test_returns_cached_host_by_id(self, temp_mngr_ctx: MngrContext) -> None:
        host_id = str(HostId())
        agents = [_make_agent_data(host_id=host_id, host_name="cached-host")]
        provider, _ = _make_provider(temp_mngr_ctx, fake_agents=agents)
        provider.list_hosts(cg=temp_mngr_ctx.concurrency_group)

        host = provider.get_host(HostId(host_id))

        assert isinstance(host, RemoteHost)
        assert host.get_name() == HostName("cached-host")

    def test_returns_cached_host_by_name(self, temp_mngr_ctx: MngrContext) -> None:
        agents = [_make_agent_data(host_name="find-me")]
        provider, _ = _make_provider(temp_mngr_ctx, fake_agents=agents)
        provider.list_hosts(cg=temp_mngr_ctx.concurrency_group)

        host = provider.get_host(HostName("find-me"))

        assert isinstance(host, RemoteHost)

    def test_raises_not_found_when_cache_empty(self, temp_mngr_ctx: MngrContext) -> None:
        provider, _ = _make_provider(temp_mngr_ctx)

        with pytest.raises(HostNotFoundError):
            provider.get_host(HostId(str(HostId())))

    def test_raises_not_found_for_unknown_id(self, temp_mngr_ctx: MngrContext) -> None:
        agents = [_make_agent_data(host_name="known-host")]
        provider, _ = _make_provider(temp_mngr_ctx, fake_agents=agents)
        provider.list_hosts(cg=temp_mngr_ctx.concurrency_group)

        with pytest.raises(HostNotFoundError):
            provider.get_host(HostId(str(HostId())))


class TestListPersistedAgentData:
    def test_returns_cached_data(self, temp_mngr_ctx: MngrContext) -> None:
        host_id = str(HostId())
        agent_id = str(AgentId())
        agents = [_make_agent_data(host_id=host_id, agent_id=agent_id)]
        provider, _ = _make_provider(temp_mngr_ctx, fake_agents=agents)
        provider.list_hosts(cg=temp_mngr_ctx.concurrency_group)

        data = provider.list_persisted_agent_data_for_host(HostId(host_id))

        assert len(data) == 1
        assert data[0]["id"] == agent_id

    def test_fetches_from_api_when_cache_empty(self, temp_mngr_ctx: MngrContext) -> None:
        host_id = str(HostId())
        agent_id = str(AgentId())
        agents = [_make_agent_data(host_id=host_id, agent_id=agent_id)]
        provider, _ = _make_provider(temp_mngr_ctx, fake_agents=agents)
        # Don't call list_hosts() -- cache is empty

        data = provider.list_persisted_agent_data_for_host(HostId(host_id))

        assert len(data) == 1
        assert data[0]["id"] == agent_id

    def test_raises_when_api_unreachable(self, temp_mngr_ctx: MngrContext) -> None:
        provider, _ = _make_provider(temp_mngr_ctx, should_raise=True)

        with pytest.raises(ProviderError, match="Connection refused"):
            provider.list_persisted_agent_data_for_host(HostId(str(HostId())))
