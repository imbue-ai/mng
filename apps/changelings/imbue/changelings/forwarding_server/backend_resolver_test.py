from imbue.changelings.forwarding_server.backend_resolver import StaticBackendResolver
from imbue.changelings.primitives import ChangelingName


def test_get_backend_url_returns_url_for_known_changeling() -> None:
    resolver = StaticBackendResolver(
        url_by_changeling_name={"elena-turing": "http://localhost:3001"},
    )
    url = resolver.get_backend_url(ChangelingName("elena-turing"))
    assert url == "http://localhost:3001"


def test_get_backend_url_returns_none_for_unknown_changeling() -> None:
    resolver = StaticBackendResolver(
        url_by_changeling_name={"elena-turing": "http://localhost:3001"},
    )
    url = resolver.get_backend_url(ChangelingName("unknown-agent"))
    assert url is None


def test_list_known_changeling_names_returns_sorted_names() -> None:
    resolver = StaticBackendResolver(
        url_by_changeling_name={
            "code-reviewer": "http://localhost:3002",
            "agent-alpha": "http://localhost:3001",
        },
    )
    names = resolver.list_known_changeling_names()
    assert names == (ChangelingName("agent-alpha"), ChangelingName("code-reviewer"))


def test_list_known_changeling_names_returns_empty_tuple_when_no_agents() -> None:
    resolver = StaticBackendResolver(url_by_changeling_name={})
    names = resolver.list_known_changeling_names()
    assert names == ()
