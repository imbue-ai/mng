from inline_snapshot import snapshot

from imbue.changelings.forwarding_server.proxy import generate_bootstrap_html
from imbue.changelings.forwarding_server.proxy import generate_service_worker_js
from imbue.changelings.forwarding_server.proxy import generate_websocket_shim_js
from imbue.changelings.forwarding_server.proxy import rewrite_absolute_paths_in_html
from imbue.changelings.forwarding_server.proxy import rewrite_cookie_path
from imbue.changelings.forwarding_server.proxy import rewrite_proxied_html
from imbue.mng.primitives import AgentId

_TEST_AGENT: AgentId = AgentId("agent-00000000000000000000000000000001")
_TEST_AGENT_2: AgentId = AgentId("agent-00000000000000000000000000000002")


def test_generate_bootstrap_html_contains_service_worker_registration() -> None:
    html = generate_bootstrap_html(_TEST_AGENT)
    assert "serviceWorker.register" in html
    assert f"/agents/{_TEST_AGENT}/" in html
    assert "__sw.js" in html


def test_generate_bootstrap_html_sets_sw_cookie() -> None:
    html = generate_bootstrap_html(_TEST_AGENT)
    assert f"sw_installed_{_TEST_AGENT}" in html


def test_generate_service_worker_js_contains_prefix() -> None:
    js = generate_service_worker_js(_TEST_AGENT)
    assert f"const PREFIX = '/agents/{_TEST_AGENT}'" in js
    assert "skipWaiting" in js
    assert "clients.claim" in js


def test_generate_service_worker_js_rewrites_fetch_urls() -> None:
    js = generate_service_worker_js(_TEST_AGENT_2)
    assert "url.pathname = PREFIX + url.pathname" in js


def test_generate_websocket_shim_js_contains_prefix() -> None:
    js = generate_websocket_shim_js(_TEST_AGENT)
    assert f"var PREFIX = '/agents/{_TEST_AGENT}'" in js
    assert "OrigWebSocket" in js


def test_rewrite_cookie_path_with_root_path() -> None:
    result = rewrite_cookie_path(
        set_cookie_header="sid=abc; Path=/",
        agent_id=_TEST_AGENT,
    )
    assert result == snapshot("sid=abc; Path=/agents/agent-00000000000000000000000000000001/")


def test_rewrite_cookie_path_with_subpath() -> None:
    result = rewrite_cookie_path(
        set_cookie_header="sid=abc; Path=/api",
        agent_id=_TEST_AGENT,
    )
    assert result == snapshot("sid=abc; Path=/agents/agent-00000000000000000000000000000001/api")


def test_rewrite_cookie_path_without_path_attribute() -> None:
    result = rewrite_cookie_path(
        set_cookie_header="sid=abc",
        agent_id=_TEST_AGENT,
    )
    assert result == snapshot("sid=abc; Path=/agents/agent-00000000000000000000000000000001/")


def test_rewrite_cookie_path_does_not_double_prefix() -> None:
    result = rewrite_cookie_path(
        set_cookie_header=f"sid=abc; Path=/agents/{_TEST_AGENT}/api",
        agent_id=_TEST_AGENT,
    )
    assert result == snapshot("sid=abc; Path=/agents/agent-00000000000000000000000000000001/api")


# -- Absolute path rewriting --


def test_rewrite_absolute_paths_rewrites_href() -> None:
    html = '<a href="/hello.txt">link</a>'
    result = rewrite_absolute_paths_in_html(
        html_content=html,
        agent_id=_TEST_AGENT,
    )
    assert result == snapshot('<a href="/agents/agent-00000000000000000000000000000001/hello.txt">link</a>')


def test_rewrite_absolute_paths_rewrites_src() -> None:
    html = '<img src="/images/logo.png">'
    result = rewrite_absolute_paths_in_html(
        html_content=html,
        agent_id=_TEST_AGENT,
    )
    assert result == snapshot('<img src="/agents/agent-00000000000000000000000000000001/images/logo.png">')


def test_rewrite_absolute_paths_rewrites_action() -> None:
    html = '<form action="/submit">'
    result = rewrite_absolute_paths_in_html(
        html_content=html,
        agent_id=_TEST_AGENT,
    )
    assert result == snapshot('<form action="/agents/agent-00000000000000000000000000000001/submit">')


def test_rewrite_absolute_paths_preserves_relative_urls() -> None:
    html = '<a href="hello.txt">link</a>'
    result = rewrite_absolute_paths_in_html(
        html_content=html,
        agent_id=_TEST_AGENT,
    )
    assert result == snapshot('<a href="hello.txt">link</a>')


def test_rewrite_absolute_paths_preserves_protocol_relative_urls() -> None:
    html = '<a href="//example.com/page">link</a>'
    result = rewrite_absolute_paths_in_html(
        html_content=html,
        agent_id=_TEST_AGENT,
    )
    assert result == snapshot('<a href="//example.com/page">link</a>')


def test_rewrite_absolute_paths_preserves_full_urls() -> None:
    html = '<a href="https://example.com/page">link</a>'
    result = rewrite_absolute_paths_in_html(
        html_content=html,
        agent_id=_TEST_AGENT,
    )
    assert result == snapshot('<a href="https://example.com/page">link</a>')


def test_rewrite_absolute_paths_does_not_double_prefix() -> None:
    html = f'<a href="/agents/{_TEST_AGENT}/hello.txt">link</a>'
    result = rewrite_absolute_paths_in_html(
        html_content=html,
        agent_id=_TEST_AGENT,
    )
    assert result == snapshot('<a href="/agents/agent-00000000000000000000000000000001/hello.txt">link</a>')


def test_rewrite_absolute_paths_handles_single_quotes() -> None:
    html = "<a href='/hello.txt'>link</a>"
    result = rewrite_absolute_paths_in_html(
        html_content=html,
        agent_id=_TEST_AGENT,
    )
    assert result == snapshot("<a href='/agents/agent-00000000000000000000000000000001/hello.txt'>link</a>")


# -- Full proxied HTML rewriting --


def test_rewrite_proxied_html_injects_base_tag_and_shim() -> None:
    html = "<html><head><title>Test</title></head><body></body></html>"
    result = rewrite_proxied_html(
        html_content=html,
        agent_id=_TEST_AGENT,
    )
    assert f'<base href="/agents/{_TEST_AGENT}/">' in result
    assert "OrigWebSocket" in result
    assert "<title>Test</title>" in result


def test_rewrite_proxied_html_rewrites_absolute_paths() -> None:
    html = '<html><head></head><body><a href="/page">link</a></body></html>'
    result = rewrite_proxied_html(
        html_content=html,
        agent_id=_TEST_AGENT,
    )
    assert f'href="/agents/{_TEST_AGENT}/page"' in result


def test_rewrite_proxied_html_with_head_attributes() -> None:
    html = '<html><head lang="en"><title>Test</title></head><body></body></html>'
    result = rewrite_proxied_html(
        html_content=html,
        agent_id=_TEST_AGENT,
    )
    assert f'<head lang="en"><base href="/agents/{_TEST_AGENT}/">' in result


def test_rewrite_proxied_html_without_head_tag() -> None:
    html = "<html><body>Hello</body></html>"
    result = rewrite_proxied_html(
        html_content=html,
        agent_id=_TEST_AGENT,
    )
    assert result.startswith(f'<base href="/agents/{_TEST_AGENT}/">')
    assert "<html><body>Hello</body></html>" in result
