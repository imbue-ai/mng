"""Unit tests for Host implementation."""

import json
from pathlib import Path

import pytest

from imbue.mngr.hosts.host import Host
from imbue.mngr.primitives import AgentId
from imbue.mngr.primitives import AgentName
from imbue.mngr.primitives import HostName
from imbue.mngr.providers.local.instance import LocalProviderInstance


@pytest.fixture
def host_with_agents_dir(
    local_provider: LocalProviderInstance,
    temp_host_dir: Path,
) -> tuple[Host, Path]:
    """Create a Host with an agents directory for testing."""
    host = local_provider.create_host(HostName("test-agent-refs"))
    assert isinstance(host, Host)
    agents_dir = temp_host_dir / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    return host, agents_dir


def test_get_agent_references_returns_refs_with_certified_data(
    host_with_agents_dir: tuple[Host, Path],
) -> None:
    """Test that get_agent_references returns refs with certified_data populated."""
    host, agents_dir = host_with_agents_dir

    # Create agent data
    agent_id = AgentId.generate()
    agent_dir = agents_dir / str(agent_id)
    agent_dir.mkdir()
    agent_data = {
        "id": str(agent_id),
        "name": "test-agent",
        "type": "claude",
        "permissions": ["read", "write"],
        "work_dir": "/tmp/work",
    }
    (agent_dir / "data.json").write_text(json.dumps(agent_data))

    refs = host.get_agent_references()

    assert len(refs) == 1
    assert refs[0].agent_id == agent_id
    assert refs[0].agent_name == AgentName("test-agent")
    assert refs[0].host_id == host.id
    assert refs[0].certified_data == agent_data
    assert refs[0].agent_type == "claude"
    assert refs[0].permissions == ("read", "write")
    assert refs[0].work_dir == Path("/tmp/work")


def test_get_agent_references_returns_empty_when_no_agents_dir(
    local_provider: LocalProviderInstance,
) -> None:
    """Test that get_agent_references returns empty list when no agents directory exists."""
    host = local_provider.create_host(HostName("test-no-agents"))
    assert isinstance(host, Host)

    # Don't create agents directory
    refs = host.get_agent_references()

    assert refs == []


def test_get_agent_references_skips_missing_data_json(
    host_with_agents_dir: tuple[Host, Path],
) -> None:
    """Test that get_agent_references skips agent dirs without data.json."""
    host, agents_dir = host_with_agents_dir

    # Create agent directory without data.json
    agent_id = AgentId.generate()
    agent_dir = agents_dir / str(agent_id)
    agent_dir.mkdir()
    # Don't create data.json

    refs = host.get_agent_references()

    assert refs == []


def test_get_agent_references_skips_invalid_json(
    host_with_agents_dir: tuple[Host, Path],
) -> None:
    """Test that get_agent_references skips agent dirs with invalid JSON."""
    host, agents_dir = host_with_agents_dir

    # Create agent with invalid JSON
    agent_id = AgentId.generate()
    agent_dir = agents_dir / str(agent_id)
    agent_dir.mkdir()
    (agent_dir / "data.json").write_text("not valid json {{{")

    refs = host.get_agent_references()

    assert refs == []


def test_get_agent_references_skips_missing_id(
    host_with_agents_dir: tuple[Host, Path],
) -> None:
    """Test that get_agent_references skips records with missing id."""
    host, agents_dir = host_with_agents_dir

    # Create agent data without id
    agent_id = AgentId.generate()
    agent_dir = agents_dir / str(agent_id)
    agent_dir.mkdir()
    agent_data = {"name": "test-agent"}  # Missing id
    (agent_dir / "data.json").write_text(json.dumps(agent_data))

    refs = host.get_agent_references()

    assert refs == []


def test_get_agent_references_skips_missing_name(
    host_with_agents_dir: tuple[Host, Path],
) -> None:
    """Test that get_agent_references skips records with missing name."""
    host, agents_dir = host_with_agents_dir

    # Create agent data without name
    agent_id = AgentId.generate()
    agent_dir = agents_dir / str(agent_id)
    agent_dir.mkdir()
    agent_data = {"id": str(agent_id)}  # Missing name
    (agent_dir / "data.json").write_text(json.dumps(agent_data))

    refs = host.get_agent_references()

    assert refs == []


def test_get_agent_references_skips_invalid_id(
    host_with_agents_dir: tuple[Host, Path],
) -> None:
    """Test that get_agent_references skips records with invalid id format."""
    host, agents_dir = host_with_agents_dir

    # Create agent data with invalid id
    agent_id = AgentId.generate()
    agent_dir = agents_dir / str(agent_id)
    agent_dir.mkdir()
    agent_data = {"id": "", "name": "test-agent"}  # Empty id
    (agent_dir / "data.json").write_text(json.dumps(agent_data))

    refs = host.get_agent_references()

    assert refs == []


def test_get_agent_references_skips_invalid_name(
    host_with_agents_dir: tuple[Host, Path],
) -> None:
    """Test that get_agent_references skips records with invalid name format."""
    host, agents_dir = host_with_agents_dir

    # Create agent data with invalid name
    agent_id = AgentId.generate()
    agent_dir = agents_dir / str(agent_id)
    agent_dir.mkdir()
    agent_data = {"id": str(agent_id), "name": ""}  # Empty name
    (agent_dir / "data.json").write_text(json.dumps(agent_data))

    refs = host.get_agent_references()

    assert refs == []


def test_get_agent_references_loads_multiple_agents(
    host_with_agents_dir: tuple[Host, Path],
) -> None:
    """Test that get_agent_references loads all valid agents."""
    host, agents_dir = host_with_agents_dir

    # Create multiple agents
    agent_ids = [AgentId.generate() for _ in range(3)]
    for i, agent_id in enumerate(agent_ids):
        agent_dir = agents_dir / str(agent_id)
        agent_dir.mkdir()
        agent_data = {"id": str(agent_id), "name": f"agent-{i}"}
        (agent_dir / "data.json").write_text(json.dumps(agent_data))

    refs = host.get_agent_references()

    assert len(refs) == 3
    ref_ids = {ref.agent_id for ref in refs}
    assert ref_ids == set(agent_ids)


def test_get_agent_references_skips_bad_records_but_loads_good_ones(
    host_with_agents_dir: tuple[Host, Path],
) -> None:
    """Test that get_agent_references skips bad records but still loads good ones."""
    host, agents_dir = host_with_agents_dir

    # Create a good agent
    good_id = AgentId.generate()
    good_dir = agents_dir / str(good_id)
    good_dir.mkdir()
    (good_dir / "data.json").write_text(json.dumps({"id": str(good_id), "name": "good-agent"}))

    # Create a bad agent (missing name)
    bad_id = AgentId.generate()
    bad_dir = agents_dir / str(bad_id)
    bad_dir.mkdir()
    (bad_dir / "data.json").write_text(json.dumps({"id": str(bad_id)}))  # Missing name

    # Create another good agent
    good_id_2 = AgentId.generate()
    good_dir_2 = agents_dir / str(good_id_2)
    good_dir_2.mkdir()
    (good_dir_2 / "data.json").write_text(json.dumps({"id": str(good_id_2), "name": "good-agent-2"}))

    refs = host.get_agent_references()

    # Should have 2 good agents, bad one skipped
    assert len(refs) == 2
    ref_ids = {ref.agent_id for ref in refs}
    assert good_id in ref_ids
    assert good_id_2 in ref_ids
    assert bad_id not in ref_ids
