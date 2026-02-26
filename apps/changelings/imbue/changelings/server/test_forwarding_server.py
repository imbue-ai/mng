from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from fastapi import Request as FastAPIRequest
from fastapi.responses import HTMLResponse
from fastapi.responses import JSONResponse
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from imbue.changelings.primitives import ChangelingName
from imbue.changelings.primitives import OneTimeCode
from imbue.changelings.server.app import create_forwarding_server
from imbue.changelings.server.auth import FileAuthStore
from imbue.changelings.server.backend_resolver import StaticBackendResolver
from imbue.changelings.server.cookie_manager import get_cookie_name_for_changeling


def _create_test_backend() -> FastAPI:
    """Create a simple backend app for proxy testing."""
    backend = FastAPI()

    @backend.get("/")
    def backend_root() -> HTMLResponse:
        return HTMLResponse("<html><head><title>Backend</title></head><body>Hello from backend</body></html>")

    @backend.get("/api/status")
    def backend_status() -> JSONResponse:
        return JSONResponse({"status": "ok"})

    @backend.post("/api/echo")
    async def backend_echo(request: FastAPIRequest) -> JSONResponse:
        body = await request.body()
        return JSONResponse({"echo": body.decode()})

    return backend


def _create_test_forwarding_server(
    tmp_path: Path,
    url_by_changeling_name: dict[str, str],
    http_client: httpx.AsyncClient | None,
) -> tuple[TestClient, FileAuthStore, StaticBackendResolver]:
    """Create a forwarding server with the given backend configuration."""
    auth_dir = tmp_path / "auth"
    auth_store = FileAuthStore(data_directory=auth_dir)
    backend_resolver = StaticBackendResolver(url_by_changeling_name=url_by_changeling_name)

    app = create_forwarding_server(
        auth_store=auth_store,
        backend_resolver=backend_resolver,
        http_client=http_client,
    )
    client = TestClient(app)

    return client, auth_store, backend_resolver


def _setup_test_server(
    tmp_path: Path,
) -> tuple[TestClient, FileAuthStore, ChangelingName, StaticBackendResolver]:
    """Set up a forwarding server with a test backend for proxy testing."""
    changeling_name = ChangelingName(f"test-agent-{uuid4().hex}")

    backend_app = _create_test_backend()
    test_http_client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=backend_app),
        base_url="http://test-backend",
    )

    client, auth_store, backend_resolver = _create_test_forwarding_server(
        tmp_path=tmp_path,
        url_by_changeling_name={str(changeling_name): "http://test-backend"},
        http_client=test_http_client,
    )

    return client, auth_store, changeling_name, backend_resolver


def _authenticate_client(
    client: TestClient,
    auth_store: FileAuthStore,
    changeling_name: ChangelingName,
) -> None:
    """Authenticate a test client for a changeling by adding a code and consuming it."""
    code = OneTimeCode(f"auth-{uuid4().hex}")
    auth_store.add_one_time_code(changeling_name=changeling_name, code=code)
    client.get(
        "/authenticate",
        params={"changeling_name": str(changeling_name), "one_time_code": str(code)},
        follow_redirects=False,
    )


def test_landing_page_shows_empty_state_without_cookies(tmp_path: Path) -> None:
    client, _, _, _ = _setup_test_server(tmp_path)

    response = client.get("/")

    assert response.status_code == 200
    assert "No changelings are accessible" in response.text


def test_login_redirects_to_authenticate_via_js(tmp_path: Path) -> None:
    client, auth_store, changeling_name, _ = _setup_test_server(tmp_path)
    code = OneTimeCode(f"login-code-{uuid4().hex}")
    auth_store.add_one_time_code(changeling_name=changeling_name, code=code)

    response = client.get(
        "/login",
        params={"changeling_name": str(changeling_name), "one_time_code": str(code)},
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert "window.location.href" in response.text
    assert "/authenticate" in response.text


def test_authenticate_with_valid_code_sets_cookie_and_redirects(tmp_path: Path) -> None:
    client, auth_store, changeling_name, _ = _setup_test_server(tmp_path)
    code = OneTimeCode(f"auth-code-{uuid4().hex}")
    auth_store.add_one_time_code(changeling_name=changeling_name, code=code)

    response = client.get(
        "/authenticate",
        params={"changeling_name": str(changeling_name), "one_time_code": str(code)},
        follow_redirects=False,
    )

    assert response.status_code == 307
    cookie_name = get_cookie_name_for_changeling(changeling_name)
    assert cookie_name in response.cookies


def test_authenticate_with_invalid_code_returns_403(tmp_path: Path) -> None:
    client, _, changeling_name, _ = _setup_test_server(tmp_path)

    response = client.get(
        "/authenticate",
        params={"changeling_name": str(changeling_name), "one_time_code": "bogus-code-82734"},
        follow_redirects=False,
    )

    assert response.status_code == 403
    assert "invalid or has already been used" in response.text


def test_authenticate_code_cannot_be_reused(tmp_path: Path) -> None:
    client, auth_store, changeling_name, _ = _setup_test_server(tmp_path)
    code = OneTimeCode(f"once-only-{uuid4().hex}")
    auth_store.add_one_time_code(changeling_name=changeling_name, code=code)

    # First use succeeds
    first_response = client.get(
        "/authenticate",
        params={"changeling_name": str(changeling_name), "one_time_code": str(code)},
        follow_redirects=False,
    )
    assert first_response.status_code == 307

    # Second use fails
    second_response = client.get(
        "/authenticate",
        params={"changeling_name": str(changeling_name), "one_time_code": str(code)},
        follow_redirects=False,
    )
    assert second_response.status_code == 403


def test_landing_page_shows_changeling_after_authentication(tmp_path: Path) -> None:
    client, auth_store, changeling_name, _ = _setup_test_server(tmp_path)
    _authenticate_client(client=client, auth_store=auth_store, changeling_name=changeling_name)

    response = client.get("/")
    assert response.status_code == 200
    assert str(changeling_name) in response.text


def test_agent_proxy_rejects_unauthenticated_requests(tmp_path: Path) -> None:
    client, _, changeling_name, _ = _setup_test_server(tmp_path)

    response = client.get(f"/agents/{changeling_name}/")
    assert response.status_code == 403


def test_agent_proxy_serves_bootstrap_on_first_navigation(tmp_path: Path) -> None:
    client, auth_store, changeling_name, _ = _setup_test_server(tmp_path)
    _authenticate_client(client=client, auth_store=auth_store, changeling_name=changeling_name)

    response = client.get(
        f"/agents/{changeling_name}/",
        headers={"sec-fetch-mode": "navigate"},
    )

    assert response.status_code == 200
    assert "serviceWorker.register" in response.text


def test_agent_proxy_serves_service_worker_js(tmp_path: Path) -> None:
    client, auth_store, changeling_name, _ = _setup_test_server(tmp_path)
    _authenticate_client(client=client, auth_store=auth_store, changeling_name=changeling_name)

    response = client.get(f"/agents/{changeling_name}/__sw.js")
    assert response.status_code == 200
    assert "application/javascript" in response.headers["content-type"]
    assert "skipWaiting" in response.text


def test_agent_proxy_forwards_get_request_to_backend(tmp_path: Path) -> None:
    client, auth_store, changeling_name, _ = _setup_test_server(tmp_path)
    _authenticate_client(client=client, auth_store=auth_store, changeling_name=changeling_name)

    # Set the SW cookie so we bypass bootstrap
    client.cookies.set(f"sw_installed_{changeling_name}", "1")

    response = client.get(f"/agents/{changeling_name}/api/status")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_agent_proxy_forwards_post_request_to_backend(tmp_path: Path) -> None:
    client, auth_store, changeling_name, _ = _setup_test_server(tmp_path)
    _authenticate_client(client=client, auth_store=auth_store, changeling_name=changeling_name)

    client.cookies.set(f"sw_installed_{changeling_name}", "1")

    response = client.post(
        f"/agents/{changeling_name}/api/echo",
        content=b"test-body-content",
    )
    assert response.status_code == 200
    assert response.json() == {"echo": "test-body-content"}


def test_agent_proxy_injects_websocket_shim_into_html_responses(tmp_path: Path) -> None:
    client, auth_store, changeling_name, _ = _setup_test_server(tmp_path)
    _authenticate_client(client=client, auth_store=auth_store, changeling_name=changeling_name)

    client.cookies.set(f"sw_installed_{changeling_name}", "1")

    response = client.get(f"/agents/{changeling_name}/")
    assert response.status_code == 200
    assert "OrigWebSocket" in response.text
    assert "Hello from backend" in response.text


def _setup_test_server_without_backend(
    tmp_path: Path,
) -> tuple[TestClient, FileAuthStore, ChangelingName]:
    """Set up a forwarding server with no backends for testing error paths."""
    changeling_name = ChangelingName(f"no-backend-{uuid4().hex}")

    client, auth_store, _ = _create_test_forwarding_server(
        tmp_path=tmp_path,
        url_by_changeling_name={},
        http_client=None,
    )

    _authenticate_client(client=client, auth_store=auth_store, changeling_name=changeling_name)

    return client, auth_store, changeling_name


def test_agent_proxy_returns_502_for_unknown_backend(tmp_path: Path) -> None:
    client, _, changeling_name = _setup_test_server_without_backend(tmp_path)

    client.cookies.set(f"sw_installed_{changeling_name}", "1")

    response = client.get(f"/agents/{changeling_name}/")
    assert response.status_code == 502


def test_login_redirects_if_already_authenticated(tmp_path: Path) -> None:
    client, auth_store, changeling_name, _ = _setup_test_server(tmp_path)
    _authenticate_client(client=client, auth_store=auth_store, changeling_name=changeling_name)

    new_code = OneTimeCode(f"second-code-{uuid4().hex}")
    auth_store.add_one_time_code(changeling_name=changeling_name, code=new_code)

    response = client.get(
        "/login",
        params={"changeling_name": str(changeling_name), "one_time_code": str(new_code)},
        follow_redirects=False,
    )
    assert response.status_code == 307
    assert response.headers["location"] == "/"


def test_websocket_proxy_rejects_unauthenticated_connection(tmp_path: Path) -> None:
    client, _, changeling_name, _ = _setup_test_server(tmp_path)

    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(f"/agents/{changeling_name}/ws"):
            pass

    assert exc_info.value.code == 4003


def test_websocket_proxy_rejects_unknown_backend(tmp_path: Path) -> None:
    client, _, changeling_name = _setup_test_server_without_backend(tmp_path)

    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(f"/agents/{changeling_name}/ws"):
            pass

    assert exc_info.value.code == 4004
