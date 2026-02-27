import asyncio
from collections.abc import AsyncGenerator
from collections.abc import Mapping
from contextlib import asynccontextmanager
from typing import Annotated
from typing import Final

import httpx
import websockets
from fastapi import Depends
from fastapi import FastAPI
from fastapi import Request
from fastapi import WebSocket
from fastapi import WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.responses import Response
from loguru import logger
from websockets import ClientConnection

from imbue.changelings.forwarding_server.auth import AuthStoreInterface
from imbue.changelings.forwarding_server.backend_resolver import BackendResolverInterface
from imbue.changelings.forwarding_server.cookie_manager import create_signed_cookie_value
from imbue.changelings.forwarding_server.cookie_manager import get_cookie_name_for_agent
from imbue.changelings.forwarding_server.cookie_manager import verify_signed_cookie_value
from imbue.changelings.forwarding_server.proxy import generate_bootstrap_html
from imbue.changelings.forwarding_server.proxy import generate_service_worker_js
from imbue.changelings.forwarding_server.proxy import rewrite_cookie_path
from imbue.changelings.forwarding_server.proxy import rewrite_proxied_html
from imbue.changelings.forwarding_server.templates import render_agent_servers_page
from imbue.changelings.forwarding_server.templates import render_auth_error_page
from imbue.changelings.forwarding_server.templates import render_landing_page
from imbue.changelings.forwarding_server.templates import render_login_redirect_page
from imbue.changelings.primitives import OneTimeCode
from imbue.changelings.primitives import ServerName
from imbue.mng.primitives import AgentId

_PROXY_TIMEOUT_SECONDS: Final[float] = 30.0

_EXCLUDED_RESPONSE_HEADERS: Final[frozenset[str]] = frozenset(
    {
        "transfer-encoding",
        "content-encoding",
        "content-length",
    }
)


# -- Dependency injection helpers --


def _get_auth_store(request: Request) -> AuthStoreInterface:
    return request.app.state.auth_store


def _get_backend_resolver(request: Request) -> BackendResolverInterface:
    return request.app.state.backend_resolver


AuthStoreDep = Annotated[AuthStoreInterface, Depends(_get_auth_store)]
BackendResolverDep = Annotated[BackendResolverInterface, Depends(_get_backend_resolver)]


# -- Auth helpers --


def _check_auth_cookie(
    cookies: Mapping[str, str],
    agent_id: AgentId,
    auth_store: AuthStoreInterface,
) -> bool:
    """Check whether the given cookies contain a valid auth cookie for the agent."""
    signing_key = auth_store.get_signing_key()
    cookie_name = get_cookie_name_for_agent(agent_id)
    cookie_value = cookies.get(cookie_name)
    if cookie_value is None:
        return False
    verified = verify_signed_cookie_value(
        cookie_value=cookie_value,
        signing_key=signing_key,
    )
    return verified == agent_id


def _get_authenticated_agent_ids(
    cookies: Mapping[str, str],
    auth_store: AuthStoreInterface,
    backend_resolver: BackendResolverInterface,
) -> list[AgentId]:
    """Extract agent IDs from valid auth cookies."""
    signing_key = auth_store.get_signing_key()
    known_ids = auth_store.list_agent_ids_with_valid_codes()
    resolver_ids = backend_resolver.list_known_agent_ids()

    all_candidate_ids: set[str] = set()
    for agent_id in known_ids:
        all_candidate_ids.add(str(agent_id))
    for agent_id in resolver_ids:
        all_candidate_ids.add(str(agent_id))

    authenticated: list[AgentId] = []
    for candidate_id_str in sorted(all_candidate_ids):
        candidate_id = AgentId(candidate_id_str)
        cookie_name = get_cookie_name_for_agent(candidate_id)
        cookie_value = cookies.get(cookie_name)
        if cookie_value is not None:
            verified = verify_signed_cookie_value(
                cookie_value=cookie_value,
                signing_key=signing_key,
            )
            if verified == candidate_id:
                authenticated.append(candidate_id)

    return authenticated


# -- WebSocket forwarding helpers --


async def _forward_client_to_backend(
    client_websocket: WebSocket,
    backend_ws: ClientConnection,
) -> None:
    """Forward messages from the client WebSocket to the backend.

    Terminates via WebSocketDisconnect (client disconnects) or
    ConnectionClosed (backend disconnects).
    """
    try:
        while True:
            data = await client_websocket.receive()
            if "text" in data:
                await backend_ws.send(data["text"])
            elif "bytes" in data:
                await backend_ws.send(data["bytes"])
            else:
                pass
    except WebSocketDisconnect:
        await backend_ws.close()
    except websockets.exceptions.ConnectionClosed:
        logger.debug("Backend WebSocket closed while forwarding client message")


async def _forward_backend_to_client(
    client_websocket: WebSocket,
    backend_ws: ClientConnection,
    agent_id: AgentId,
) -> None:
    """Forward messages from the backend WebSocket to the client."""
    try:
        async for msg in backend_ws:
            if isinstance(msg, str):
                await client_websocket.send_text(msg)
            else:
                await client_websocket.send_bytes(msg)
    except websockets.exceptions.ConnectionClosed:
        logger.debug("Backend WebSocket closed for {}", agent_id)


# -- Lifespan --


@asynccontextmanager
async def _managed_lifespan(
    inner_app: FastAPI,
    is_externally_managed_client: bool,
) -> AsyncGenerator[None, None]:
    """Manage the httpx client lifecycle for the forwarding server."""
    if not is_externally_managed_client:
        inner_app.state.http_client = httpx.AsyncClient(
            follow_redirects=False,
            timeout=_PROXY_TIMEOUT_SECONDS,
        )
    try:
        yield
    finally:
        if not is_externally_managed_client:
            await inner_app.state.http_client.aclose()


# -- Route handlers (module-level, using Depends for dependency injection) --


def _handle_login(
    agent_id: str,
    one_time_code: str,
    request: Request,
    auth_store: AuthStoreDep,
) -> Response:
    parsed_id = AgentId(agent_id)
    code = OneTimeCode(one_time_code)

    # If user already has a valid cookie, redirect to landing page
    if _check_auth_cookie(cookies=request.cookies, agent_id=parsed_id, auth_store=auth_store):
        return Response(status_code=307, headers={"Location": "/"})

    # Render JS redirect to /authenticate (prevents prefetch consumption)
    html = render_login_redirect_page(agent_id=parsed_id, one_time_code=code)
    return HTMLResponse(content=html)


def _handle_authenticate(
    agent_id: str,
    one_time_code: str,
    auth_store: AuthStoreDep,
) -> Response:
    parsed_id = AgentId(agent_id)
    code = OneTimeCode(one_time_code)

    is_valid = auth_store.validate_and_consume_code(agent_id=parsed_id, code=code)

    if not is_valid:
        html = render_auth_error_page(message="This login code is invalid or has already been used.")
        return HTMLResponse(content=html, status_code=403)

    # Set signed cookie
    signing_key = auth_store.get_signing_key()
    cookie_value = create_signed_cookie_value(agent_id=parsed_id, signing_key=signing_key)
    cookie_name = get_cookie_name_for_agent(parsed_id)

    response = Response(status_code=307, headers={"Location": f"/agents/{parsed_id}/"})
    response.set_cookie(
        key=cookie_name,
        value=cookie_value,
        path="/",
        httponly=True,
        samesite="lax",
    )
    return response


def _handle_landing_page(
    request: Request,
    auth_store: AuthStoreDep,
    backend_resolver: BackendResolverDep,
) -> Response:
    authenticated_ids = _get_authenticated_agent_ids(
        cookies=request.cookies,
        auth_store=auth_store,
        backend_resolver=backend_resolver,
    )
    html = render_landing_page(accessible_agent_ids=authenticated_ids)
    return HTMLResponse(content=html)


def _handle_agent_servers_page(
    agent_id: str,
    request: Request,
    auth_store: AuthStoreDep,
    backend_resolver: BackendResolverDep,
) -> Response:
    """Show a listing of all available servers for a given agent."""
    parsed_id = AgentId(agent_id)

    if not _check_auth_cookie(cookies=request.cookies, agent_id=parsed_id, auth_store=auth_store):
        return Response(status_code=403, content="Not authenticated for this changeling")

    server_names = backend_resolver.list_servers_for_agent(parsed_id)
    html = render_agent_servers_page(agent_id=parsed_id, server_names=server_names)
    return HTMLResponse(content=html)


async def _forward_http_request(
    request: Request,
    backend_url: str,
    path: str,
    agent_id: str,
    server_name: str,
) -> httpx.Response | Response:
    """Forward an HTTP request to the backend, returning the backend response or an error Response."""
    proxy_url = f"{backend_url}/{path}"
    if request.url.query:
        proxy_url += f"?{request.url.query}"

    headers = dict(request.headers)
    headers.pop("host", None)

    body = await request.body()

    active_http_client: httpx.AsyncClient = request.app.state.http_client
    try:
        return await active_http_client.request(
            method=request.method,
            url=proxy_url,
            headers=headers,
            content=body,
        )
    except httpx.ConnectError:
        logger.debug("Backend connection refused for {} server {}", agent_id, server_name)
        return Response(status_code=502, content="Backend connection refused")
    except httpx.TimeoutException:
        logger.debug("Backend request timed out for {} server {}", agent_id, server_name)
        return Response(status_code=504, content="Backend request timed out")


def _build_proxy_response(
    backend_response: httpx.Response,
    agent_id: AgentId,
    server_name: ServerName,
) -> Response:
    """Transform a backend httpx response into a FastAPI Response with header/content rewriting."""
    # Build response headers, dropping hop-by-hop headers
    resp_headers: dict[str, list[str]] = {}
    for header_key, header_value in backend_response.headers.multi_items():
        if header_key.lower() in _EXCLUDED_RESPONSE_HEADERS:
            continue
        if header_key.lower() == "set-cookie":
            header_value = rewrite_cookie_path(
                set_cookie_header=header_value,
                agent_id=agent_id,
                server_name=server_name,
            )
        resp_headers.setdefault(header_key, [])
        resp_headers[header_key].append(header_value)

    content: str | bytes = backend_response.content

    # Rewrite HTML responses (absolute paths, base tag, WS shim)
    content_type = backend_response.headers.get("content-type", "")
    if "text/html" in content_type:
        html_text = backend_response.text
        rewritten_html = rewrite_proxied_html(
            html_content=html_text,
            agent_id=agent_id,
            server_name=server_name,
        )
        content = rewritten_html.encode()

    response = Response(content=content, status_code=backend_response.status_code)
    for header_key, header_values in resp_headers.items():
        for header_value in header_values:
            response.headers.append(header_key, header_value)
    return response


async def _handle_proxy_http(
    agent_id: str,
    server_name: str,
    path: str,
    request: Request,
    auth_store: AuthStoreDep,
    backend_resolver: BackendResolverDep,
) -> Response:
    parsed_id = AgentId(agent_id)
    parsed_server = ServerName(server_name)

    # Check auth (per-agent, not per-server)
    if not _check_auth_cookie(cookies=request.cookies, agent_id=parsed_id, auth_store=auth_store):
        return Response(status_code=403, content="Not authenticated for this changeling")

    # Serve the service worker script
    if path == "__sw.js":
        return Response(
            content=generate_service_worker_js(parsed_id, parsed_server),
            media_type="application/javascript",
        )

    backend_url = backend_resolver.get_backend_url(parsed_id, parsed_server)
    if backend_url is None:
        return Response(
            status_code=502,
            content=f"Backend unavailable for agent {agent_id}, server {server_name}",
        )

    # Check if SW is installed via cookie (scoped per server)
    sw_cookie = request.cookies.get(f"sw_installed_{agent_id}_{server_name}")
    is_navigation = request.headers.get("sec-fetch-mode") == "navigate"

    # First HTML navigation without SW -> serve bootstrap
    if is_navigation and not sw_cookie:
        return HTMLResponse(generate_bootstrap_html(parsed_id, parsed_server))

    # Forward request to backend
    result = await _forward_http_request(
        request=request,
        backend_url=backend_url,
        path=path,
        agent_id=agent_id,
        server_name=server_name,
    )

    # If forwarding returned an error Response directly, return it
    if isinstance(result, Response):
        return result

    return _build_proxy_response(
        backend_response=result,
        agent_id=parsed_id,
        server_name=parsed_server,
    )


async def _handle_proxy_websocket(
    websocket: WebSocket,
    agent_id: str,
    server_name: str,
    path: str,
    auth_store: AuthStoreInterface,
    backend_resolver: BackendResolverInterface,
) -> None:
    parsed_id = AgentId(agent_id)
    parsed_server = ServerName(server_name)

    # Check auth (per-agent)
    if not _check_auth_cookie(cookies=websocket.cookies, agent_id=parsed_id, auth_store=auth_store):
        await websocket.close(code=4003, reason="Not authenticated")
        return

    backend_url = backend_resolver.get_backend_url(parsed_id, parsed_server)
    if backend_url is None:
        await websocket.close(code=4004, reason=f"Unknown server: {agent_id}/{server_name}")
        return

    ws_backend = backend_url.replace("http://", "ws://").replace("https://", "wss://")
    ws_url = f"{ws_backend}/{path}"
    if websocket.url.query:
        ws_url += f"?{websocket.url.query}"

    await websocket.accept()

    try:
        async with websockets.connect(ws_url) as backend_ws:
            await asyncio.gather(
                _forward_client_to_backend(
                    client_websocket=websocket,
                    backend_ws=backend_ws,
                ),
                _forward_backend_to_client(
                    client_websocket=websocket,
                    backend_ws=backend_ws,
                    agent_id=parsed_id,
                ),
            )

    except (ConnectionRefusedError, OSError, TimeoutError) as connection_error:
        logger.debug(
            "Backend WebSocket connection failed for {}/{}: {}",
            agent_id,
            server_name,
            connection_error,
        )
        try:
            await websocket.close(code=1011, reason="Backend connection failed")
        except RuntimeError:
            logger.trace("WebSocket already closed when trying to send error for {}", agent_id)


# -- App factory --


def create_forwarding_server(
    auth_store: AuthStoreInterface,
    backend_resolver: BackendResolverInterface,
    http_client: httpx.AsyncClient | None,
) -> FastAPI:
    """Create the local forwarding server FastAPI application."""
    is_externally_managed_client = http_client is not None

    @asynccontextmanager
    async def _lifespan(inner_app: FastAPI) -> AsyncGenerator[None, None]:
        async with _managed_lifespan(inner_app=inner_app, is_externally_managed_client=is_externally_managed_client):
            yield

    app = FastAPI(lifespan=_lifespan)

    app.state.auth_store = auth_store
    app.state.backend_resolver = backend_resolver
    if http_client is not None:
        app.state.http_client = http_client

    # Register routes
    app.get("/login")(_handle_login)
    app.get("/authenticate")(_handle_authenticate)
    app.get("/")(_handle_landing_page)

    # Agent server listing page: /agents/{agent_id}/
    app.get("/agents/{agent_id}/")(_handle_agent_servers_page)

    # Proxy routes: /agents/{agent_id}/{server_name}/{path:path}
    app.api_route(
        "/agents/{agent_id}/{server_name}/{path:path}",
        methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"],
    )(_handle_proxy_http)

    # WebSocket route needs manual dependency wiring since Depends doesn't work on WS
    @app.websocket("/agents/{agent_id}/{server_name}/{path:path}")
    async def proxy_websocket(websocket: WebSocket, agent_id: str, server_name: str, path: str) -> None:
        await _handle_proxy_websocket(
            websocket=websocket,
            agent_id=agent_id,
            server_name=server_name,
            path=path,
            auth_store=auth_store,
            backend_resolver=backend_resolver,
        )

    return app
