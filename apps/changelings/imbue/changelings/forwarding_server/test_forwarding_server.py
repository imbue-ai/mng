import json
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from fastapi import Request as FastAPIRequest
from fastapi.responses import HTMLResponse
from fastapi.responses import JSONResponse
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from imbue.changelings.forwarding_server.app import create_forwarding_server
from imbue.changelings.forwarding_server.auth import FileAuthStore
from imbue.changelings.forwarding_server.backend_resolver import AgentLogsBackendResolver
from imbue.changelings.forwarding_server.backend_resolver import BackendResolverInterface
from imbue.changelings.forwarding_server.backend_resolver import SERVERS_LOG_FILENAME
from imbue.changelings.forwarding_server.backend_resolver import StaticBackendResolver
from imbue.changelings.forwarding_server.cookie_manager import get_cookie_name_for_agent
from imbue.changelings.primitives import OneTimeCode
from imbue.mng.primitives import AgentId


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
    url_by_agent_id: dict[str, str],
    http_client: httpx.AsyncClient | None,
) -> tuple[TestClient, FileAuthStore, StaticBackendResolver]:
    """Create a forwarding server with the given backend configuration."""
    auth_dir = tmp_path / "auth"
    auth_store = FileAuthStore(data_directory=auth_dir)
    backend_resolver = StaticBackendResolver(url_by_agent_id=url_by_agent_id)

    app = create_forwarding_server(
        auth_store=auth_store,
        backend_resolver=backend_resolver,
        http_client=http_client,
    )
    client = TestClient(app)

    return client, auth_store, backend_resolver


def _create_test_forwarding_server_with_resolver(
    tmp_path: Path,
    backend_resolver: BackendResolverInterface,
    http_client: httpx.AsyncClient | None,
) -> tuple[TestClient, FileAuthStore]:
    """Create a forwarding server with an arbitrary backend resolver."""
    auth_dir = tmp_path / "auth"
    auth_store = FileAuthStore(data_directory=auth_dir)

    app = create_forwarding_server(
        auth_store=auth_store,
        backend_resolver=backend_resolver,
        http_client=http_client,
    )
    client = TestClient(app)

    return client, auth_store


def _setup_test_server(
    tmp_path: Path,
) -> tuple[TestClient, FileAuthStore, AgentId, StaticBackendResolver]:
    """Set up a forwarding server with a test backend for proxy testing."""
    agent_id = AgentId()

    backend_app = _create_test_backend()
    test_http_client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=backend_app),
        base_url="http://test-backend",
    )

    client, auth_store, backend_resolver = _create_test_forwarding_server(
        tmp_path=tmp_path,
        url_by_agent_id={str(agent_id): "http://test-backend"},
        http_client=test_http_client,
    )

    return client, auth_store, agent_id, backend_resolver


def _authenticate_client(
    client: TestClient,
    auth_store: FileAuthStore,
    agent_id: AgentId,
) -> None:
    """Authenticate a test client for an agent by adding a code and consuming it."""
    code = OneTimeCode(f"auth-{AgentId()}")
    auth_store.add_one_time_code(agent_id=agent_id, code=code)
    client.get(
        "/authenticate",
        params={"agent_id": str(agent_id), "one_time_code": str(code)},
        follow_redirects=False,
    )


def test_landing_page_shows_empty_state_without_cookies(tmp_path: Path) -> None:
    client, _, _, _ = _setup_test_server(tmp_path)

    response = client.get("/")

    assert response.status_code == 200
    assert "No changelings are accessible" in response.text


def test_login_redirects_to_authenticate_via_js(tmp_path: Path) -> None:
    client, auth_store, agent_id, _ = _setup_test_server(tmp_path)
    code = OneTimeCode(f"login-code-{AgentId()}")
    auth_store.add_one_time_code(agent_id=agent_id, code=code)

    response = client.get(
        "/login",
        params={"agent_id": str(agent_id), "one_time_code": str(code)},
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert "window.location.href" in response.text
    assert "/authenticate" in response.text


def test_authenticate_with_valid_code_sets_cookie_and_redirects(tmp_path: Path) -> None:
    client, auth_store, agent_id, _ = _setup_test_server(tmp_path)
    code = OneTimeCode(f"auth-code-{AgentId()}")
    auth_store.add_one_time_code(agent_id=agent_id, code=code)

    response = client.get(
        "/authenticate",
        params={"agent_id": str(agent_id), "one_time_code": str(code)},
        follow_redirects=False,
    )

    assert response.status_code == 307
    cookie_name = get_cookie_name_for_agent(agent_id)
    assert cookie_name in response.cookies


def test_authenticate_with_invalid_code_returns_403(tmp_path: Path) -> None:
    client, _, agent_id, _ = _setup_test_server(tmp_path)

    response = client.get(
        "/authenticate",
        params={"agent_id": str(agent_id), "one_time_code": "bogus-code-82734"},
        follow_redirects=False,
    )

    assert response.status_code == 403
    assert "invalid or has already been used" in response.text


def test_authenticate_code_cannot_be_reused(tmp_path: Path) -> None:
    client, auth_store, agent_id, _ = _setup_test_server(tmp_path)
    code = OneTimeCode(f"once-only-{AgentId()}")
    auth_store.add_one_time_code(agent_id=agent_id, code=code)

    first_response = client.get(
        "/authenticate",
        params={"agent_id": str(agent_id), "one_time_code": str(code)},
        follow_redirects=False,
    )
    assert first_response.status_code == 307

    second_response = client.get(
        "/authenticate",
        params={"agent_id": str(agent_id), "one_time_code": str(code)},
        follow_redirects=False,
    )
    assert second_response.status_code == 403


def test_landing_page_shows_agent_after_authentication(tmp_path: Path) -> None:
    client, auth_store, agent_id, _ = _setup_test_server(tmp_path)
    _authenticate_client(client=client, auth_store=auth_store, agent_id=agent_id)

    response = client.get("/")
    assert response.status_code == 200
    assert str(agent_id) in response.text


def test_agent_proxy_rejects_unauthenticated_requests(tmp_path: Path) -> None:
    client, _, agent_id, _ = _setup_test_server(tmp_path)

    response = client.get(f"/agents/{agent_id}/")
    assert response.status_code == 403


def test_agent_proxy_serves_bootstrap_on_first_navigation(tmp_path: Path) -> None:
    client, auth_store, agent_id, _ = _setup_test_server(tmp_path)
    _authenticate_client(client=client, auth_store=auth_store, agent_id=agent_id)

    response = client.get(
        f"/agents/{agent_id}/",
        headers={"sec-fetch-mode": "navigate"},
    )

    assert response.status_code == 200
    assert "serviceWorker.register" in response.text


def test_agent_proxy_serves_service_worker_js(tmp_path: Path) -> None:
    client, auth_store, agent_id, _ = _setup_test_server(tmp_path)
    _authenticate_client(client=client, auth_store=auth_store, agent_id=agent_id)

    response = client.get(f"/agents/{agent_id}/__sw.js")
    assert response.status_code == 200
    assert "application/javascript" in response.headers["content-type"]
    assert "skipWaiting" in response.text


def test_agent_proxy_forwards_get_request_to_backend(tmp_path: Path) -> None:
    client, auth_store, agent_id, _ = _setup_test_server(tmp_path)
    _authenticate_client(client=client, auth_store=auth_store, agent_id=agent_id)

    client.cookies.set(f"sw_installed_{agent_id}", "1")

    response = client.get(f"/agents/{agent_id}/api/status")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_agent_proxy_forwards_post_request_to_backend(tmp_path: Path) -> None:
    client, auth_store, agent_id, _ = _setup_test_server(tmp_path)
    _authenticate_client(client=client, auth_store=auth_store, agent_id=agent_id)

    client.cookies.set(f"sw_installed_{agent_id}", "1")

    response = client.post(
        f"/agents/{agent_id}/api/echo",
        content=b"test-body-content",
    )
    assert response.status_code == 200
    assert response.json() == {"echo": "test-body-content"}


def test_agent_proxy_injects_websocket_shim_into_html_responses(tmp_path: Path) -> None:
    client, auth_store, agent_id, _ = _setup_test_server(tmp_path)
    _authenticate_client(client=client, auth_store=auth_store, agent_id=agent_id)

    client.cookies.set(f"sw_installed_{agent_id}", "1")

    response = client.get(f"/agents/{agent_id}/")
    assert response.status_code == 200
    assert "OrigWebSocket" in response.text
    assert "Hello from backend" in response.text


def _setup_test_server_without_backend(
    tmp_path: Path,
) -> tuple[TestClient, FileAuthStore, AgentId]:
    """Set up a forwarding server with no backends for testing error paths."""
    agent_id = AgentId()

    client, auth_store, _ = _create_test_forwarding_server(
        tmp_path=tmp_path,
        url_by_agent_id={},
        http_client=None,
    )

    _authenticate_client(client=client, auth_store=auth_store, agent_id=agent_id)

    return client, auth_store, agent_id


def test_agent_proxy_returns_502_for_unknown_backend(tmp_path: Path) -> None:
    client, _, agent_id = _setup_test_server_without_backend(tmp_path)

    client.cookies.set(f"sw_installed_{agent_id}", "1")

    response = client.get(f"/agents/{agent_id}/")
    assert response.status_code == 502


def test_login_redirects_if_already_authenticated(tmp_path: Path) -> None:
    client, auth_store, agent_id, _ = _setup_test_server(tmp_path)
    _authenticate_client(client=client, auth_store=auth_store, agent_id=agent_id)

    new_code = OneTimeCode(f"second-code-{AgentId()}")
    auth_store.add_one_time_code(agent_id=agent_id, code=new_code)

    response = client.get(
        "/login",
        params={"agent_id": str(agent_id), "one_time_code": str(new_code)},
        follow_redirects=False,
    )
    assert response.status_code == 307
    assert response.headers["location"] == "/"


def test_websocket_proxy_rejects_unauthenticated_connection(tmp_path: Path) -> None:
    client, _, agent_id, _ = _setup_test_server(tmp_path)

    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(f"/agents/{agent_id}/ws"):
            pass

    assert exc_info.value.code == 4003


def test_websocket_proxy_rejects_unknown_backend(tmp_path: Path) -> None:
    client, _, agent_id = _setup_test_server_without_backend(tmp_path)

    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(f"/agents/{agent_id}/ws"):
            pass

    assert exc_info.value.code == 4004


# -- Integration test: agent writes servers.jsonl, forwarding server discovers and proxies --


def _write_server_log(host_dir: Path, agent_id: AgentId, server: str, url: str) -> None:
    """Write a server log record, simulating what an agent zygote does on startup."""
    logs_dir = host_dir / "agents" / str(agent_id) / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    with open(logs_dir / SERVERS_LOG_FILENAME, "a") as f:
        f.write(json.dumps({"server": server, "url": url}) + "\n")


def test_agent_logs_resolver_proxies_to_backend_discovered_from_servers_jsonl(tmp_path: Path) -> None:
    """Full integration test: an agent writes servers.jsonl, the AgentLogsBackendResolver
    discovers it, and the forwarding server successfully proxies HTTP requests through."""
    agent_id = AgentId()
    host_dir = tmp_path / "mng_host"
    data_dir = tmp_path / "changelings_data"

    # Simulate what the agent zygote does on startup: write to servers.jsonl
    _write_server_log(host_dir, agent_id, "web", "http://test-backend")

    # Create a test backend
    backend_app = _create_test_backend()
    test_http_client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=backend_app),
        base_url="http://test-backend",
    )

    # Create forwarding server with AgentLogsBackendResolver
    backend_resolver = AgentLogsBackendResolver(host_dir=host_dir)
    client, auth_store = _create_test_forwarding_server_with_resolver(
        tmp_path=data_dir,
        backend_resolver=backend_resolver,
        http_client=test_http_client,
    )

    # Verify the resolver discovered the agent
    assert backend_resolver.get_backend_url(agent_id) == "http://test-backend"
    assert agent_id in backend_resolver.list_known_agent_ids()

    # Authenticate
    _authenticate_client(client=client, auth_store=auth_store, agent_id=agent_id)

    # Set SW cookie to bypass bootstrap
    client.cookies.set(f"sw_installed_{agent_id}", "1")

    # Proxy a GET request
    response = client.get(f"/agents/{agent_id}/api/status")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

    # Proxy a POST request
    response = client.post(
        f"/agents/{agent_id}/api/echo",
        content=b"integration-test",
    )
    assert response.status_code == 200
    assert response.json() == {"echo": "integration-test"}


def test_agent_logs_resolver_returns_502_when_no_servers_jsonl(tmp_path: Path) -> None:
    """When an agent has no servers.jsonl, the resolver returns None and the proxy returns 502."""
    agent_id = AgentId()
    host_dir = tmp_path / "mng_host"
    data_dir = tmp_path / "changelings_data"

    # No servers.jsonl written -- the agent hasn't started yet
    backend_resolver = AgentLogsBackendResolver(host_dir=host_dir)
    client, auth_store = _create_test_forwarding_server_with_resolver(
        tmp_path=data_dir,
        backend_resolver=backend_resolver,
        http_client=None,
    )

    _authenticate_client(client=client, auth_store=auth_store, agent_id=agent_id)
    client.cookies.set(f"sw_installed_{agent_id}", "1")

    response = client.get(f"/agents/{agent_id}/")
    assert response.status_code == 502


def test_agent_logs_resolver_landing_page_shows_discovered_agents(tmp_path: Path) -> None:
    """The landing page should list agents discovered via servers.jsonl."""
    agent_id = AgentId()
    host_dir = tmp_path / "mng_host"
    data_dir = tmp_path / "changelings_data"

    # Agent writes its server info
    _write_server_log(host_dir, agent_id, "web", "http://test-backend")

    backend_resolver = AgentLogsBackendResolver(host_dir=host_dir)
    client, auth_store = _create_test_forwarding_server_with_resolver(
        tmp_path=data_dir,
        backend_resolver=backend_resolver,
        http_client=None,
    )

    _authenticate_client(client=client, auth_store=auth_store, agent_id=agent_id)

    response = client.get("/")
    assert response.status_code == 200
    assert str(agent_id) in response.text
