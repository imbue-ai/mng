from pathlib import Path

import pytest

from imbue.mng.api.find import find_all_matching_agents
from imbue.mng.api.find import find_all_matching_hosts
from imbue.mng.errors import MngError
from imbue.mng.errors import UserInputError
from imbue.mng.primitives import AgentId
from imbue.mng.primitives import AgentName
from imbue.mng.primitives import DiscoveredAgent
from imbue.mng.primitives import DiscoveredHost
from imbue.mng.primitives import HostId
from imbue.mng.primitives import HostName
from imbue.mng.primitives import ProviderInstanceName
from imbue.mng_file.cli.target import ResolveFileTargetResult
from imbue.mng_file.cli.target import _compute_agent_base_path
from imbue.mng_file.cli.target import _is_volume_accessible_path
from imbue.mng_file.cli.target import compute_volume_path
from imbue.mng_file.cli.target import resolve_full_path
from imbue.mng_file.data_types import PathRelativeTo


def _make_discovered_host(name: str = "test-host") -> DiscoveredHost:
    return DiscoveredHost(
        host_id=HostId.generate(),
        host_name=HostName(name),
        provider_name=ProviderInstanceName("local"),
    )


def _make_discovered_agent(name: str = "test-agent", host_id: HostId | None = None) -> DiscoveredAgent:
    return DiscoveredAgent(
        host_id=host_id if host_id is not None else HostId.generate(),
        agent_id=AgentId.generate(),
        agent_name=AgentName(name),
        provider_name=ProviderInstanceName("local"),
    )


# --- resolve_full_path ---


def test_resolve_full_path_with_relative_path() -> None:
    assert resolve_full_path(Path("/home/user/work"), "config.toml") == Path("/home/user/work/config.toml")


def test_resolve_full_path_with_nested_relative_path() -> None:
    assert resolve_full_path(Path("/home/user/work"), "subdir/file.txt") == Path("/home/user/work/subdir/file.txt")


def test_resolve_full_path_with_absolute_path_ignores_base() -> None:
    assert resolve_full_path(Path("/home/user/work"), "/etc/hostname") == Path("/etc/hostname")


def test_resolve_full_path_with_dot_relative_path() -> None:
    assert resolve_full_path(Path("/home/user/work"), "./local/file.txt") == Path("/home/user/work/local/file.txt")


# --- _compute_agent_base_path ---


def test_compute_agent_base_path_work() -> None:
    work_dir = Path("/agent/work")
    result = _compute_agent_base_path(PathRelativeTo.WORK, work_dir, Path("/home/.mng"), AgentId.generate())
    assert result == work_dir


def test_compute_agent_base_path_state() -> None:
    host_dir = Path("/home/user/.mng")
    agent_id = AgentId.generate()
    result = _compute_agent_base_path(PathRelativeTo.STATE, Path("/work"), host_dir, agent_id)
    assert result == host_dir / "agents" / str(agent_id)


def test_compute_agent_base_path_host() -> None:
    host_dir = Path("/home/user/.mng")
    result = _compute_agent_base_path(PathRelativeTo.HOST, Path("/work"), host_dir, AgentId.generate())
    assert result == host_dir


# --- _is_volume_accessible_path ---


def test_is_volume_accessible_path_work_returns_false() -> None:
    assert _is_volume_accessible_path(PathRelativeTo.WORK) is False


def test_is_volume_accessible_path_state_returns_true() -> None:
    assert _is_volume_accessible_path(PathRelativeTo.STATE) is True


def test_is_volume_accessible_path_host_returns_true() -> None:
    assert _is_volume_accessible_path(PathRelativeTo.HOST) is True


# --- compute_volume_path ---


def test_compute_volume_path_host_with_user_path() -> None:
    assert (
        compute_volume_path(PathRelativeTo.HOST, agent_id=None, user_path="events/logs/events.jsonl")
        == "events/logs/events.jsonl"
    )


def test_compute_volume_path_host_without_user_path() -> None:
    assert compute_volume_path(PathRelativeTo.HOST, agent_id=None, user_path=None) == "."


def test_compute_volume_path_state_with_user_path() -> None:
    agent_id = AgentId.generate()
    assert (
        compute_volume_path(PathRelativeTo.STATE, agent_id=agent_id, user_path="file.txt")
        == f"agents/{agent_id}/file.txt"
    )


def test_compute_volume_path_state_without_user_path() -> None:
    agent_id = AgentId.generate()
    assert compute_volume_path(PathRelativeTo.STATE, agent_id=agent_id, user_path=None) == f"agents/{agent_id}"


def test_compute_volume_path_state_without_agent_id_raises() -> None:
    with pytest.raises(UserInputError, match="requires an agent target"):
        compute_volume_path(PathRelativeTo.STATE, agent_id=None, user_path="file.txt")


def test_compute_volume_path_work_raises() -> None:
    with pytest.raises(UserInputError, match="offline"):
        compute_volume_path(PathRelativeTo.WORK, agent_id=AgentId.generate(), user_path="file.txt")


# --- ResolveFileTargetResult ---


def test_resolve_file_target_result_host_raises_when_offline() -> None:
    result = ResolveFileTargetResult(
        online_host=None,
        volume=None,
        base_path=Path("/test"),
        is_agent=False,
        agent_id=None,
        relative_to=PathRelativeTo.HOST,
    )
    with pytest.raises(MngError, match="offline"):
        _ = result.host


def test_resolve_file_target_result_is_online_false_when_no_host() -> None:
    result = ResolveFileTargetResult(
        online_host=None,
        volume=None,
        base_path=Path("/test"),
        is_agent=False,
        agent_id=None,
        relative_to=PathRelativeTo.HOST,
    )
    assert result.is_online is False


# --- find_all_matching_agents ---


def testfind_all_matching_agents_by_name() -> None:
    host = _make_discovered_host()
    agent = _make_discovered_agent(name="my-agent")
    result = find_all_matching_agents("my-agent", {host: [agent]})
    assert len(result) == 1
    assert result[0] == (host, agent)


def testfind_all_matching_agents_by_id() -> None:
    host = _make_discovered_host()
    agent = _make_discovered_agent()
    result = find_all_matching_agents(str(agent.agent_id), {host: [agent]})
    assert len(result) == 1


def testfind_all_matching_agents_no_match() -> None:
    host = _make_discovered_host()
    agent = _make_discovered_agent(name="other-agent")
    result = find_all_matching_agents("nonexistent", {host: [agent]})
    assert len(result) == 0


def testfind_all_matching_agents_multiple_matches() -> None:
    host1 = _make_discovered_host(name="host-1")
    host2 = _make_discovered_host(name="host-2")
    agent1 = _make_discovered_agent(name="shared-name")
    agent2 = _make_discovered_agent(name="shared-name")
    result = find_all_matching_agents("shared-name", {host1: [agent1], host2: [agent2]})
    assert len(result) == 2


# --- find_all_matching_hosts ---


def testfind_all_matching_hosts_by_name() -> None:
    host = _make_discovered_host(name="my-host")
    result = find_all_matching_hosts("my-host", [host])
    assert len(result) == 1
    assert result[0] == host


def testfind_all_matching_hosts_by_id() -> None:
    host = _make_discovered_host()
    result = find_all_matching_hosts(str(host.host_id), [host])
    assert len(result) == 1


def testfind_all_matching_hosts_no_match() -> None:
    host = _make_discovered_host(name="other-host")
    result = find_all_matching_hosts("nonexistent", [host])
    assert len(result) == 0


def testfind_all_matching_hosts_multiple_matches() -> None:
    host1 = _make_discovered_host(name="shared-name")
    host2 = _make_discovered_host(name="shared-name")
    result = find_all_matching_hosts("shared-name", [host1, host2])
    assert len(result) == 2
