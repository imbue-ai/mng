from imbue.changelings.forwarding_server.backend_resolver import MngCliBackendResolver
from imbue.changelings.forwarding_server.backend_resolver import MngCliInterface
from imbue.changelings.forwarding_server.backend_resolver import StaticBackendResolver
from imbue.changelings.forwarding_server.backend_resolver import _parse_agent_ids_from_json
from imbue.changelings.forwarding_server.backend_resolver import _parse_server_log_records
from imbue.changelings.forwarding_server.conftest import FakeMngCli
from imbue.changelings.forwarding_server.conftest import make_agents_json
from imbue.changelings.forwarding_server.conftest import make_server_log
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


# -- _parse_server_log_records tests --


def test_parse_server_log_records_parses_valid_jsonl() -> None:
    text = '{"server": "web", "url": "http://127.0.0.1:9100"}\n'
    records = _parse_server_log_records(text)

    assert len(records) == 1
    assert records[0].server == "web"
    assert records[0].url == "http://127.0.0.1:9100"


def test_parse_server_log_records_returns_empty_for_empty_input() -> None:
    assert _parse_server_log_records("") == []
    assert _parse_server_log_records("\n") == []


def test_parse_server_log_records_skips_invalid_lines() -> None:
    text = 'bad line\n{"server": "web", "url": "http://127.0.0.1:9100"}\n'
    records = _parse_server_log_records(text)

    assert len(records) == 1
    assert records[0].url == "http://127.0.0.1:9100"


def test_parse_server_log_records_returns_multiple_records() -> None:
    text = '{"server": "web", "url": "http://127.0.0.1:9100"}\n{"server": "web", "url": "http://127.0.0.1:9200"}\n'
    records = _parse_server_log_records(text)

    assert len(records) == 2
    assert records[-1].url == "http://127.0.0.1:9200"


# -- _parse_agent_ids_from_json tests --


def test_parse_agent_ids_from_json_parses_valid_output() -> None:
    json_output = make_agents_json(_AGENT_A, _AGENT_B)
    ids = _parse_agent_ids_from_json(json_output)

    assert _AGENT_A in ids
    assert _AGENT_B in ids


def test_parse_agent_ids_from_json_returns_empty_for_none() -> None:
    assert _parse_agent_ids_from_json(None) == ()


def test_parse_agent_ids_from_json_returns_empty_for_invalid_json() -> None:
    assert _parse_agent_ids_from_json("not json") == ()


# -- MngCliBackendResolver tests (using FakeMngCli) --


def test_mng_cli_resolver_returns_url_from_server_log() -> None:
    fake_cli = FakeMngCli(
        server_logs={str(_AGENT_A): make_server_log("web", "http://127.0.0.1:9100")},
        agents_json=make_agents_json(_AGENT_A),
    )
    resolver = MngCliBackendResolver(mng_cli=fake_cli)

    assert resolver.get_backend_url(_AGENT_A) == "http://127.0.0.1:9100"


def test_mng_cli_resolver_returns_none_for_unknown_agent() -> None:
    fake_cli = FakeMngCli(server_logs={}, agents_json=make_agents_json())
    resolver = MngCliBackendResolver(mng_cli=fake_cli)

    assert resolver.get_backend_url(_AGENT_A) is None


def test_mng_cli_resolver_returns_most_recent_url() -> None:
    log_content = make_server_log("web", "http://127.0.0.1:9100") + make_server_log("web", "http://127.0.0.1:9200")
    fake_cli = FakeMngCli(
        server_logs={str(_AGENT_A): log_content},
        agents_json=make_agents_json(_AGENT_A),
    )
    resolver = MngCliBackendResolver(mng_cli=fake_cli)

    assert resolver.get_backend_url(_AGENT_A) == "http://127.0.0.1:9200"


def test_mng_cli_resolver_lists_known_agents() -> None:
    fake_cli = FakeMngCli(
        server_logs={},
        agents_json=make_agents_json(_AGENT_A, _AGENT_B),
    )
    resolver = MngCliBackendResolver(mng_cli=fake_cli)
    ids = resolver.list_known_agent_ids()

    assert _AGENT_A in ids
    assert _AGENT_B in ids


def test_mng_cli_resolver_returns_empty_when_no_agents() -> None:
    fake_cli = FakeMngCli(server_logs={}, agents_json=make_agents_json())
    resolver = MngCliBackendResolver(mng_cli=fake_cli)

    assert resolver.list_known_agent_ids() == ()


def test_mng_cli_resolver_returns_empty_when_mng_list_fails() -> None:
    fake_cli = FakeMngCli(server_logs={}, agents_json=None)
    resolver = MngCliBackendResolver(mng_cli=fake_cli)

    assert resolver.list_known_agent_ids() == ()


def test_mng_cli_resolver_caches_backend_url() -> None:
    call_count = 0

    class CountingMngCli(MngCliInterface):
        server_logs: dict[str, str]
        agents_json: str | None = None

        def read_agent_log(self, agent_id: AgentId, log_file: str) -> str | None:
            nonlocal call_count
            call_count += 1
            return self.server_logs.get(str(agent_id))

        def list_agents_json(self) -> str | None:
            return self.agents_json

    fake_cli = CountingMngCli(
        server_logs={str(_AGENT_A): make_server_log("web", "http://127.0.0.1:9100")},
    )
    resolver = MngCliBackendResolver(mng_cli=fake_cli)

    url1 = resolver.get_backend_url(_AGENT_A)
    url2 = resolver.get_backend_url(_AGENT_A)

    assert url1 == "http://127.0.0.1:9100"
    assert url2 == "http://127.0.0.1:9100"
    assert call_count == 1
