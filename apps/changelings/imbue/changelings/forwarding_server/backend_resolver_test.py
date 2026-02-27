import json
from pathlib import Path

from imbue.changelings.forwarding_server.backend_resolver import FileBackendResolver
from imbue.changelings.forwarding_server.backend_resolver import StaticBackendResolver
from imbue.changelings.forwarding_server.backend_resolver import register_backend
from imbue.mng.primitives import AgentId

_AGENT_A: AgentId = AgentId("agent-00000000000000000000000000000001")
_AGENT_B: AgentId = AgentId("agent-00000000000000000000000000000002")


def test_get_backend_url_returns_url_for_known_agent() -> None:
    resolver = StaticBackendResolver(
        url_by_agent_id={str(_AGENT_A): "http://localhost:3001"},
    )
    url = resolver.get_backend_url(_AGENT_A)
    assert url == "http://localhost:3001"


def test_get_backend_url_returns_none_for_unknown_agent() -> None:
    resolver = StaticBackendResolver(
        url_by_agent_id={str(_AGENT_A): "http://localhost:3001"},
    )
    url = resolver.get_backend_url(_AGENT_B)
    assert url is None


def test_list_known_agent_ids_returns_sorted_ids() -> None:
    resolver = StaticBackendResolver(
        url_by_agent_id={
            str(_AGENT_B): "http://localhost:3002",
            str(_AGENT_A): "http://localhost:3001",
        },
    )
    ids = resolver.list_known_agent_ids()
    assert ids == (_AGENT_A, _AGENT_B)


def test_list_known_agent_ids_returns_empty_tuple_when_no_agents() -> None:
    resolver = StaticBackendResolver(url_by_agent_id={})
    ids = resolver.list_known_agent_ids()
    assert ids == ()


def test_file_resolver_returns_url_from_file(tmp_path: Path) -> None:
    backends_file = tmp_path / "backends.json"
    backends_file.write_text(json.dumps({str(_AGENT_A): "http://localhost:9100"}))

    resolver = FileBackendResolver(backends_path=backends_file)

    assert resolver.get_backend_url(_AGENT_A) == "http://localhost:9100"
    assert resolver.get_backend_url(_AGENT_B) is None


def test_file_resolver_returns_none_when_file_missing(tmp_path: Path) -> None:
    resolver = FileBackendResolver(backends_path=tmp_path / "nonexistent.json")

    assert resolver.get_backend_url(_AGENT_A) is None


def test_file_resolver_lists_known_agents(tmp_path: Path) -> None:
    backends_file = tmp_path / "backends.json"
    backends_file.write_text(
        json.dumps(
            {
                str(_AGENT_B): "http://localhost:9101",
                str(_AGENT_A): "http://localhost:9100",
            }
        )
    )

    resolver = FileBackendResolver(backends_path=backends_file)
    ids = resolver.list_known_agent_ids()

    assert ids == (_AGENT_A, _AGENT_B)


def test_file_resolver_returns_empty_for_missing_file(tmp_path: Path) -> None:
    resolver = FileBackendResolver(backends_path=tmp_path / "nonexistent.json")
    ids = resolver.list_known_agent_ids()

    assert ids == ()


def test_file_resolver_handles_invalid_json(tmp_path: Path) -> None:
    backends_file = tmp_path / "backends.json"
    backends_file.write_text("not json")

    resolver = FileBackendResolver(backends_path=backends_file)

    assert resolver.get_backend_url(_AGENT_A) is None
    assert resolver.list_known_agent_ids() == ()


def test_register_backend_creates_file(tmp_path: Path) -> None:
    backends_file = tmp_path / "backends.json"

    register_backend(backends_file, _AGENT_A, "http://localhost:9100")

    data = json.loads(backends_file.read_text())
    assert data[str(_AGENT_A)] == "http://localhost:9100"


def test_register_backend_adds_to_existing_file(tmp_path: Path) -> None:
    backends_file = tmp_path / "backends.json"
    backends_file.write_text(json.dumps({str(_AGENT_A): "http://localhost:9100"}))

    register_backend(backends_file, _AGENT_B, "http://localhost:9101")

    data = json.loads(backends_file.read_text())
    assert data[str(_AGENT_A)] == "http://localhost:9100"
    assert data[str(_AGENT_B)] == "http://localhost:9101"


def test_register_backend_updates_existing_entry(tmp_path: Path) -> None:
    backends_file = tmp_path / "backends.json"
    backends_file.write_text(json.dumps({str(_AGENT_A): "http://localhost:9100"}))

    register_backend(backends_file, _AGENT_A, "http://localhost:9200")

    data = json.loads(backends_file.read_text())
    assert data[str(_AGENT_A)] == "http://localhost:9200"


def test_register_backend_creates_parent_directories(tmp_path: Path) -> None:
    backends_file = tmp_path / "subdir" / "backends.json"

    register_backend(backends_file, _AGENT_A, "http://localhost:9100")

    assert backends_file.exists()
    data = json.loads(backends_file.read_text())
    assert data[str(_AGENT_A)] == "http://localhost:9100"
