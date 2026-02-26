from inline_snapshot import snapshot

from imbue.changelings.primitives import ChangelingName
from imbue.changelings.server.proxy import generate_bootstrap_html
from imbue.changelings.server.proxy import generate_service_worker_js
from imbue.changelings.server.proxy import generate_websocket_shim_js
from imbue.changelings.server.proxy import inject_websocket_shim_into_html
from imbue.changelings.server.proxy import rewrite_cookie_path


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


def test_inject_websocket_shim_into_html_with_head_tag() -> None:
    html = "<html><head><title>Test</title></head><body></body></html>"
    result = inject_websocket_shim_into_html(
        html_content=html,
        changeling_name=ChangelingName("test-agent"),
    )
    assert result.startswith("<html><head><script>")
    assert "OrigWebSocket" in result
    assert "<title>Test</title>" in result


def test_inject_websocket_shim_into_html_with_head_attributes() -> None:
    html = '<html><head lang="en"><title>Test</title></head><body></body></html>'
    result = inject_websocket_shim_into_html(
        html_content=html,
        changeling_name=ChangelingName("test-agent"),
    )
    assert '<head lang="en"><script>' in result


def test_inject_websocket_shim_into_html_without_head_tag() -> None:
    html = "<html><body>Hello</body></html>"
    result = inject_websocket_shim_into_html(
        html_content=html,
        changeling_name=ChangelingName("test-agent"),
    )
    assert result.startswith("<script>")
    assert "<html><body>Hello</body></html>" in result
