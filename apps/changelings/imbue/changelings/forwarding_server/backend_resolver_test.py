from pathlib import Path

from imbue.changelings.forwarding_server.backend_resolver import AgentLogsBackendResolver
from imbue.changelings.forwarding_server.backend_resolver import SERVERS_LOG_FILENAME
from imbue.changelings.forwarding_server.backend_resolver import StaticBackendResolver
from imbue.changelings.forwarding_server.testing import write_server_log
from imbue.mng.primitives import AgentId

_AGENT_A: AgentId = AgentId("agent-00000000000000000000000000000001")
_AGENT_B: AgentId = AgentId("agent-00000000000000000000000000000002")


# -- StaticBackendResolver tests --


def test_static_get_backend_url_returns_url_for_known_agent() -> None:
    resolver = StaticBackendResolver(
        url_by_agent_id={str(_AGENT_A): "http://localhost:3001"},
    )
    url = resolver.get_backend_url(_AGENT_A)
    assert url == "http://localhost:3001"


def test_static_get_backend_url_returns_none_for_unknown_agent() -> None:
    resolver = StaticBackendResolver(
        url_by_agent_id={str(_AGENT_A): "http://localhost:3001"},
    )
    url = resolver.get_backend_url(_AGENT_B)
    assert url is None


def test_static_list_known_agent_ids_returns_sorted_ids() -> None:
    resolver = StaticBackendResolver(
        url_by_agent_id={
            str(_AGENT_B): "http://localhost:3002",
            str(_AGENT_A): "http://localhost:3001",
        },
    )
    ids = resolver.list_known_agent_ids()
    assert ids == (_AGENT_A, _AGENT_B)


def test_static_list_known_agent_ids_returns_empty_tuple_when_no_agents() -> None:
    resolver = StaticBackendResolver(url_by_agent_id={})
    ids = resolver.list_known_agent_ids()
    assert ids == ()


# -- AgentLogsBackendResolver tests --


def test_agent_logs_resolver_returns_url_from_server_log(tmp_path: Path) -> None:
    write_server_log(tmp_path, _AGENT_A, "web", "http://localhost:9100")

    resolver = AgentLogsBackendResolver(host_dir=tmp_path)

    assert resolver.get_backend_url(_AGENT_A) == "http://localhost:9100"


def test_agent_logs_resolver_returns_none_for_unknown_agent(tmp_path: Path) -> None:
    resolver = AgentLogsBackendResolver(host_dir=tmp_path)

    assert resolver.get_backend_url(_AGENT_A) is None


def test_agent_logs_resolver_returns_none_when_no_agents_dir(tmp_path: Path) -> None:
    resolver = AgentLogsBackendResolver(host_dir=tmp_path)

    assert resolver.get_backend_url(_AGENT_A) is None


def test_agent_logs_resolver_returns_most_recent_url(tmp_path: Path) -> None:
    write_server_log(tmp_path, _AGENT_A, "web", "http://localhost:9100")
    write_server_log(tmp_path, _AGENT_A, "web", "http://localhost:9200")

    resolver = AgentLogsBackendResolver(host_dir=tmp_path)

    assert resolver.get_backend_url(_AGENT_A) == "http://localhost:9200"


def test_agent_logs_resolver_lists_known_agents(tmp_path: Path) -> None:
    write_server_log(tmp_path, _AGENT_B, "web", "http://localhost:9101")
    write_server_log(tmp_path, _AGENT_A, "web", "http://localhost:9100")

    resolver = AgentLogsBackendResolver(host_dir=tmp_path)
    ids = resolver.list_known_agent_ids()

    assert ids == (_AGENT_A, _AGENT_B)


def test_agent_logs_resolver_returns_empty_when_no_agents(tmp_path: Path) -> None:
    resolver = AgentLogsBackendResolver(host_dir=tmp_path)
    ids = resolver.list_known_agent_ids()

    assert ids == ()


def test_agent_logs_resolver_ignores_agents_without_server_logs(tmp_path: Path) -> None:
    write_server_log(tmp_path, _AGENT_A, "web", "http://localhost:9100")

    # Create agent B's directory but without servers.jsonl
    agent_b_dir = tmp_path / "agents" / str(_AGENT_B)
    agent_b_dir.mkdir(parents=True)

    resolver = AgentLogsBackendResolver(host_dir=tmp_path)
    ids = resolver.list_known_agent_ids()

    assert ids == (_AGENT_A,)


def test_agent_logs_resolver_handles_invalid_jsonl(tmp_path: Path) -> None:
    logs_dir = tmp_path / "agents" / str(_AGENT_A) / "logs"
    logs_dir.mkdir(parents=True)
    (logs_dir / SERVERS_LOG_FILENAME).write_text("not valid json\n")

    resolver = AgentLogsBackendResolver(host_dir=tmp_path)

    assert resolver.get_backend_url(_AGENT_A) is None


def test_agent_logs_resolver_skips_invalid_lines_keeps_valid(tmp_path: Path) -> None:
    logs_dir = tmp_path / "agents" / str(_AGENT_A) / "logs"
    logs_dir.mkdir(parents=True)
    content = 'bad line\n{"server": "web", "url": "http://localhost:9100"}\n'
    (logs_dir / SERVERS_LOG_FILENAME).write_text(content)

    resolver = AgentLogsBackendResolver(host_dir=tmp_path)

    assert resolver.get_backend_url(_AGENT_A) == "http://localhost:9100"


def test_agent_logs_resolver_handles_empty_file(tmp_path: Path) -> None:
    logs_dir = tmp_path / "agents" / str(_AGENT_A) / "logs"
    logs_dir.mkdir(parents=True)
    (logs_dir / SERVERS_LOG_FILENAME).write_text("")

    resolver = AgentLogsBackendResolver(host_dir=tmp_path)

    assert resolver.get_backend_url(_AGENT_A) is None
