from imbue.changelings.forwarding_server.backend_resolver import StaticBackendResolver
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
