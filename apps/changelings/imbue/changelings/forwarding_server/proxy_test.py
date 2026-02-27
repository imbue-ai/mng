from inline_snapshot import snapshot

from imbue.changelings.forwarding_server.proxy import generate_bootstrap_html
from imbue.changelings.forwarding_server.proxy import generate_service_worker_js
from imbue.changelings.forwarding_server.proxy import generate_websocket_shim_js
from imbue.changelings.forwarding_server.proxy import rewrite_absolute_paths_in_html
from imbue.changelings.forwarding_server.proxy import rewrite_cookie_path
from imbue.changelings.forwarding_server.proxy import rewrite_proxied_html
from imbue.changelings.primitives import ChangelingName


def test_generate_bootstrap_html_contains_service_worker_registration() -> None:
    name = ChangelingName("elena-turing")
    html = generate_bootstrap_html(name)
    assert "serviceWorker.register" in html
    assert "/agents/elena-turing/" in html
    assert "__sw.js" in html


def test_generate_bootstrap_html_sets_sw_cookie() -> None:
    name = ChangelingName("elena-turing")
    html = generate_bootstrap_html(name)
    assert "sw_installed_elena-turing" in html


def test_generate_service_worker_js_contains_prefix() -> None:
    name = ChangelingName("elena-turing")
    js = generate_service_worker_js(name)
    assert "const PREFIX = '/agents/elena-turing'" in js
    assert "skipWaiting" in js
    assert "clients.claim" in js


def test_generate_service_worker_js_rewrites_fetch_urls() -> None:
    name = ChangelingName("test-agent")
    js = generate_service_worker_js(name)
    assert "url.pathname = PREFIX + url.pathname" in js


def test_generate_websocket_shim_js_contains_prefix() -> None:
    name = ChangelingName("elena-turing")
    js = generate_websocket_shim_js(name)
    assert "var PREFIX = '/agents/elena-turing'" in js
    assert "OrigWebSocket" in js


def test_rewrite_cookie_path_with_root_path() -> None:
    result = rewrite_cookie_path(
        set_cookie_header="sid=abc; Path=/",
        changeling_name=ChangelingName("elena-turing"),
    )
    assert result == snapshot("sid=abc; Path=/agents/elena-turing/")


def test_rewrite_cookie_path_with_subpath() -> None:
    result = rewrite_cookie_path(
        set_cookie_header="sid=abc; Path=/api",
        changeling_name=ChangelingName("elena-turing"),
    )
    assert result == snapshot("sid=abc; Path=/agents/elena-turing/api")


def test_rewrite_cookie_path_without_path_attribute() -> None:
    result = rewrite_cookie_path(
        set_cookie_header="sid=abc",
        changeling_name=ChangelingName("elena-turing"),
    )
    assert result == snapshot("sid=abc; Path=/agents/elena-turing/")


def test_rewrite_cookie_path_does_not_double_prefix() -> None:
    result = rewrite_cookie_path(
        set_cookie_header="sid=abc; Path=/agents/elena-turing/api",
        changeling_name=ChangelingName("elena-turing"),
    )
    assert result == snapshot("sid=abc; Path=/agents/elena-turing/api")


# -- Absolute path rewriting --


def test_rewrite_absolute_paths_rewrites_href() -> None:
    html = '<a href="/hello.txt">link</a>'
    result = rewrite_absolute_paths_in_html(
        html_content=html,
        changeling_name=ChangelingName("test-agent"),
    )
    assert result == snapshot('<a href="/agents/test-agent/hello.txt">link</a>')


def test_rewrite_absolute_paths_rewrites_src() -> None:
    html = '<img src="/images/logo.png">'
    result = rewrite_absolute_paths_in_html(
        html_content=html,
        changeling_name=ChangelingName("test-agent"),
    )
    assert result == snapshot('<img src="/agents/test-agent/images/logo.png">')


def test_rewrite_absolute_paths_rewrites_action() -> None:
    html = '<form action="/submit">'
    result = rewrite_absolute_paths_in_html(
        html_content=html,
        changeling_name=ChangelingName("test-agent"),
    )
    assert result == snapshot('<form action="/agents/test-agent/submit">')


def test_rewrite_absolute_paths_preserves_relative_urls() -> None:
    html = '<a href="hello.txt">link</a>'
    result = rewrite_absolute_paths_in_html(
        html_content=html,
        changeling_name=ChangelingName("test-agent"),
    )
    assert result == snapshot('<a href="hello.txt">link</a>')


def test_rewrite_absolute_paths_preserves_protocol_relative_urls() -> None:
    html = '<a href="//example.com/page">link</a>'
    result = rewrite_absolute_paths_in_html(
        html_content=html,
        changeling_name=ChangelingName("test-agent"),
    )
    assert result == snapshot('<a href="//example.com/page">link</a>')


def test_rewrite_absolute_paths_preserves_full_urls() -> None:
    html = '<a href="https://example.com/page">link</a>'
    result = rewrite_absolute_paths_in_html(
        html_content=html,
        changeling_name=ChangelingName("test-agent"),
    )
    assert result == snapshot('<a href="https://example.com/page">link</a>')


def test_rewrite_absolute_paths_does_not_double_prefix() -> None:
    html = '<a href="/agents/test-agent/hello.txt">link</a>'
    result = rewrite_absolute_paths_in_html(
        html_content=html,
        changeling_name=ChangelingName("test-agent"),
    )
    assert result == snapshot('<a href="/agents/test-agent/hello.txt">link</a>')


def test_rewrite_absolute_paths_handles_single_quotes() -> None:
    html = "<a href='/hello.txt'>link</a>"
    result = rewrite_absolute_paths_in_html(
        html_content=html,
        changeling_name=ChangelingName("test-agent"),
    )
    assert result == snapshot("<a href='/agents/test-agent/hello.txt'>link</a>")


# -- Full proxied HTML rewriting --


def test_rewrite_proxied_html_injects_base_tag_and_shim() -> None:
    html = "<html><head><title>Test</title></head><body></body></html>"
    result = rewrite_proxied_html(
        html_content=html,
        changeling_name=ChangelingName("test-agent"),
    )
    assert '<base href="/agents/test-agent/">' in result
    assert "OrigWebSocket" in result
    assert "<title>Test</title>" in result


def test_rewrite_proxied_html_rewrites_absolute_paths() -> None:
    html = '<html><head></head><body><a href="/page">link</a></body></html>'
    result = rewrite_proxied_html(
        html_content=html,
        changeling_name=ChangelingName("test-agent"),
    )
    assert 'href="/agents/test-agent/page"' in result


def test_rewrite_proxied_html_with_head_attributes() -> None:
    html = '<html><head lang="en"><title>Test</title></head><body></body></html>'
    result = rewrite_proxied_html(
        html_content=html,
        changeling_name=ChangelingName("test-agent"),
    )
    assert '<head lang="en"><base href="/agents/test-agent/">' in result


def test_rewrite_proxied_html_without_head_tag() -> None:
    html = "<html><body>Hello</body></html>"
    result = rewrite_proxied_html(
        html_content=html,
        changeling_name=ChangelingName("test-agent"),
    )
    assert result.startswith('<base href="/agents/test-agent/">')
    assert "<html><body>Hello</body></html>" in result
