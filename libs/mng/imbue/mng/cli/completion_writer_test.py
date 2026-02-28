import json
from pathlib import Path

from imbue.mng.cli.completion_writer import AGENT_COMPLETIONS_CACHE_FILENAME
from imbue.mng.cli.completion_writer import read_provider_names_for_identifiers
from imbue.mng.cli.completion_writer import write_agent_names_cache
from imbue.mng.primitives import AgentId
from imbue.mng.primitives import AgentName
from imbue.mng.primitives import AgentReference
from imbue.mng.primitives import HostId
from imbue.mng.primitives import HostName
from imbue.mng.primitives import HostReference
from imbue.mng.primitives import ProviderInstanceName

# =============================================================================
# Helpers
# =============================================================================


def _build_agents_by_host(
    agents: list[tuple[str, str, str]],
) -> tuple[dict[HostReference, list[AgentReference]], dict[str, AgentId]]:
    """Build an agents_by_host mapping from (agent_name, provider, host_name) tuples.

    Returns the mapping and a dict of agent_name -> agent_id for lookup in tests.
    """
    result: dict[HostReference, list[AgentReference]] = {}
    ids_by_name: dict[str, AgentId] = {}
    for agent_name, provider_name, host_name in agents:
        host_id = HostId.generate()
        host_ref = HostReference(
            host_id=host_id,
            host_name=HostName(host_name),
            provider_name=ProviderInstanceName(provider_name),
        )
        agent_id = AgentId.generate()
        ids_by_name[agent_name] = agent_id
        agent_ref = AgentReference(
            host_id=host_id,
            agent_id=agent_id,
            agent_name=AgentName(agent_name),
            provider_name=ProviderInstanceName(provider_name),
        )
        result.setdefault(host_ref, []).append(agent_ref)
    return result, ids_by_name


# =============================================================================
# write_agent_names_cache format tests
# =============================================================================


def test_write_agent_names_cache_produces_agents_and_names_keys(
    tmp_path: Path,
) -> None:
    agents_by_host, _ = _build_agents_by_host(
        [
            ("bench-ep-cache4", "modal", "bench-host"),
            ("my-agent", "docker", "my-docker-host"),
        ]
    )
    write_agent_names_cache(tmp_path, agents_by_host)

    cache_path = tmp_path / AGENT_COMPLETIONS_CACHE_FILENAME
    cache_data = json.loads(cache_path.read_text())

    assert "agents" in cache_data
    assert "names" in cache_data
    assert "updated_at" in cache_data
    assert len(cache_data["agents"]) == 2
    assert cache_data["names"] == ["bench-ep-cache4", "my-agent"]


def test_write_agent_names_cache_agents_contain_provider_info(
    tmp_path: Path,
) -> None:
    agents_by_host, _ = _build_agents_by_host(
        [
            ("test-agent", "modal", "test-host"),
        ]
    )
    write_agent_names_cache(tmp_path, agents_by_host)

    cache_path = tmp_path / AGENT_COMPLETIONS_CACHE_FILENAME
    cache_data = json.loads(cache_path.read_text())
    entry = cache_data["agents"][0]

    assert entry["name"] == "test-agent"
    assert entry["provider"] == "modal"
    assert entry["host_name"] == "test-host"
    assert "id" in entry
    assert "host_id" in entry


# =============================================================================
# read_provider_names_for_identifiers tests
# =============================================================================


def test_read_provider_names_round_trip_by_name(
    tmp_path: Path,
) -> None:
    agents_by_host, _ = _build_agents_by_host(
        [
            ("bench-ep-cache4", "modal", "bench-host"),
            ("my-agent", "docker", "my-docker-host"),
        ]
    )
    write_agent_names_cache(tmp_path, agents_by_host)

    result = read_provider_names_for_identifiers(tmp_path, ["bench-ep-cache4"])

    assert result is not None
    assert "modal" in result
    assert "local" in result


def test_read_provider_names_round_trip_by_id(
    tmp_path: Path,
) -> None:
    agents_by_host, ids_by_name = _build_agents_by_host(
        [
            ("bench-ep-cache4", "modal", "bench-host"),
            ("my-agent", "docker", "my-docker-host"),
        ]
    )
    write_agent_names_cache(tmp_path, agents_by_host)

    agent_id = str(ids_by_name["my-agent"])
    result = read_provider_names_for_identifiers(tmp_path, [agent_id])

    assert result is not None
    assert "docker" in result
    assert "local" in result


def test_read_provider_names_returns_union_for_multiple_identifiers(
    tmp_path: Path,
) -> None:
    agents_by_host, _ = _build_agents_by_host(
        [
            ("bench-ep-cache4", "modal", "bench-host"),
            ("my-agent", "docker", "my-docker-host"),
        ]
    )
    write_agent_names_cache(tmp_path, agents_by_host)

    result = read_provider_names_for_identifiers(tmp_path, ["bench-ep-cache4", "my-agent"])

    assert result is not None
    assert "modal" in result
    assert "docker" in result
    assert "local" in result


def test_read_provider_names_returns_none_for_missing_identifier(
    tmp_path: Path,
) -> None:
    agents_by_host, _ = _build_agents_by_host(
        [
            ("bench-ep-cache4", "modal", "bench-host"),
        ]
    )
    write_agent_names_cache(tmp_path, agents_by_host)

    result = read_provider_names_for_identifiers(tmp_path, ["nonexistent-agent"])

    assert result is None


def test_read_provider_names_returns_none_when_cache_file_missing(
    tmp_path: Path,
) -> None:
    result = read_provider_names_for_identifiers(tmp_path, ["some-agent"])

    assert result is None


def test_read_provider_names_returns_none_for_corrupt_cache_file(
    tmp_path: Path,
) -> None:
    cache_path = tmp_path / AGENT_COMPLETIONS_CACHE_FILENAME
    cache_path.write_text("not valid json {{{")

    result = read_provider_names_for_identifiers(tmp_path, ["some-agent"])

    assert result is None


def test_read_provider_names_always_includes_local(
    tmp_path: Path,
) -> None:
    agents_by_host, _ = _build_agents_by_host(
        [
            ("bench-ep-cache4", "modal", "bench-host"),
        ]
    )
    write_agent_names_cache(tmp_path, agents_by_host)

    result = read_provider_names_for_identifiers(tmp_path, ["bench-ep-cache4"])

    assert result is not None
    assert "local" in result


def test_read_provider_names_returns_none_when_agents_key_missing(
    tmp_path: Path,
) -> None:
    """Cache without the 'agents' key (old format) should return None."""
    cache_path = tmp_path / AGENT_COMPLETIONS_CACHE_FILENAME
    cache_data = {
        "names": ["bench-ep-cache4"],
        "updated_at": "2026-01-01T00:00:00+00:00",
    }
    cache_path.write_text(json.dumps(cache_data))

    result = read_provider_names_for_identifiers(tmp_path, ["bench-ep-cache4"])

    assert result is None


def test_read_provider_names_returns_none_when_any_identifier_missing(
    tmp_path: Path,
) -> None:
    """If one identifier is found but another is not, the whole result is None."""
    agents_by_host, _ = _build_agents_by_host(
        [
            ("found-agent", "modal", "bench-host"),
        ]
    )
    write_agent_names_cache(tmp_path, agents_by_host)

    result = read_provider_names_for_identifiers(tmp_path, ["found-agent", "missing-agent"])

    assert result is None
