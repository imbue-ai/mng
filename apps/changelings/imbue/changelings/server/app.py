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

from imbue.changelings.primitives import ChangelingName
from imbue.changelings.primitives import OneTimeCode
from imbue.changelings.server.auth import AuthStoreInterface
from imbue.changelings.server.backend_resolver import BackendResolverInterface
from imbue.changelings.server.cookie_manager import create_signed_cookie_value
from imbue.changelings.server.cookie_manager import get_cookie_name_for_changeling
from imbue.changelings.server.cookie_manager import verify_signed_cookie_value
from imbue.changelings.server.proxy import generate_bootstrap_html
from imbue.changelings.server.proxy import generate_service_worker_js
from imbue.changelings.server.proxy import rewrite_cookie_path
from imbue.changelings.server.proxy import rewrite_proxied_html
from imbue.changelings.server.templates import render_auth_error_page
from imbue.changelings.server.templates import render_landing_page
from imbue.changelings.server.templates import render_login_redirect_page

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
    changeling_name: ChangelingName,
    auth_store: AuthStoreInterface,
) -> bool:
    """Check whether the given cookies contain a valid auth cookie for the changeling."""
    signing_key = auth_store.get_signing_key()
    cookie_name = get_cookie_name_for_changeling(changeling_name)
    cookie_value = cookies.get(cookie_name)
    if cookie_value is None:
        return False
    verified = verify_signed_cookie_value(
        cookie_value=cookie_value,
        signing_key=signing_key,
    )
    return verified == changeling_name


def _get_authenticated_changeling_names(
    cookies: Mapping[str, str],
    auth_store: AuthStoreInterface,
    backend_resolver: BackendResolverInterface,
) -> list[ChangelingName]:
    """Extract changeling names from valid auth cookies."""
    signing_key = auth_store.get_signing_key()
    known_names = auth_store.list_changeling_names_with_valid_codes()
    resolver_names = backend_resolver.list_known_changeling_names()

    all_candidate_names: set[str] = set()
    for name in known_names:
        all_candidate_names.add(str(name))
    for name in resolver_names:
        all_candidate_names.add(str(name))

    authenticated: list[ChangelingName] = []
    for candidate_name_str in sorted(all_candidate_names):
        candidate_name = ChangelingName(candidate_name_str)
        cookie_name = get_cookie_name_for_changeling(candidate_name)
        cookie_value = cookies.get(cookie_name)
        if cookie_value is not None:
            verified = verify_signed_cookie_value(
                cookie_value=cookie_value,
                signing_key=signing_key,
            )
            if verified == candidate_name:
                authenticated.append(candidate_name)

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
    changeling_name: ChangelingName,
) -> None:
    """Forward messages from the backend WebSocket to the client."""
    try:
        async for msg in backend_ws:
            if isinstance(msg, str):
                await client_websocket.send_text(msg)
            else:
                await client_websocket.send_bytes(msg)
    except websockets.exceptions.ConnectionClosed:
        logger.debug("Backend WebSocket closed for {}", changeling_name)


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
    changeling_name: str,
    one_time_code: str,
    request: Request,
    auth_store: AuthStoreDep,
) -> Response:
    name = ChangelingName(changeling_name)
    code = OneTimeCode(one_time_code)

    # If user already has a valid cookie, redirect to landing page
    if _check_auth_cookie(cookies=request.cookies, changeling_name=name, auth_store=auth_store):
        return Response(status_code=307, headers={"Location": "/"})

    # Render JS redirect to /authenticate (prevents prefetch consumption)
    html = render_login_redirect_page(changeling_name=name, one_time_code=code)
    return HTMLResponse(content=html)


def _handle_authenticate(
    changeling_name: str,
    one_time_code: str,
    auth_store: AuthStoreDep,
) -> Response:
    name = ChangelingName(changeling_name)
    code = OneTimeCode(one_time_code)

    is_valid = auth_store.validate_and_consume_code(changeling_name=name, code=code)

    if not is_valid:
        html = render_auth_error_page(message="This login code is invalid or has already been used.")
        return HTMLResponse(content=html, status_code=403)

    # Set signed cookie
    signing_key = auth_store.get_signing_key()
    cookie_value = create_signed_cookie_value(changeling_name=name, signing_key=signing_key)
    cookie_name = get_cookie_name_for_changeling(name)

    response = Response(status_code=307, headers={"Location": f"/agents/{name}/"})
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
    authenticated_names = _get_authenticated_changeling_names(
        cookies=request.cookies,
        auth_store=auth_store,
        backend_resolver=backend_resolver,
    )
    html = render_landing_page(accessible_changeling_names=authenticated_names)
    return HTMLResponse(content=html)


async def _forward_http_request(
    request: Request,
    backend_url: str,
    path: str,
    changeling_name: str,
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
        logger.debug("Backend connection refused for {}", changeling_name)
        return Response(status_code=502, content="Backend connection refused")
    except httpx.TimeoutException:
        logger.debug("Backend request timed out for {}", changeling_name)
        return Response(status_code=504, content="Backend request timed out")


def _build_proxy_response(
    backend_response: httpx.Response,
    changeling_name: ChangelingName,
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
                changeling_name=changeling_name,
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
            changeling_name=changeling_name,
        )
        content = rewritten_html.encode()

    response = Response(content=content, status_code=backend_response.status_code)
    for header_key, header_values in resp_headers.items():
        for header_value in header_values:
            response.headers.append(header_key, header_value)
    return response


async def _handle_proxy_http(
    changeling_name: str,
    path: str,
    request: Request,
    auth_store: AuthStoreDep,
    backend_resolver: BackendResolverDep,
) -> Response:
    name = ChangelingName(changeling_name)

    # Check auth
    if not _check_auth_cookie(cookies=request.cookies, changeling_name=name, auth_store=auth_store):
        return Response(status_code=403, content="Not authenticated for this changeling")

    # Serve the service worker script
    if path == "__sw.js":
        return Response(
            content=generate_service_worker_js(name),
            media_type="application/javascript",
        )

    backend_url = backend_resolver.get_backend_url(name)
    if backend_url is None:
        return Response(status_code=502, content=f"Backend unavailable for changeling: {changeling_name}")

    # Check if SW is installed via cookie
    sw_cookie = request.cookies.get(f"sw_installed_{changeling_name}")
    is_navigation = request.headers.get("sec-fetch-mode") == "navigate"

    # First HTML navigation without SW -> serve bootstrap
    if is_navigation and not sw_cookie:
        return HTMLResponse(generate_bootstrap_html(name))

    # Forward request to backend
    result = await _forward_http_request(
        request=request,
        backend_url=backend_url,
        path=path,
        changeling_name=changeling_name,
    )

    # If forwarding returned an error Response directly, return it
    if isinstance(result, Response):
        return result

    return _build_proxy_response(backend_response=result, changeling_name=name)


async def _handle_proxy_websocket(
    websocket: WebSocket,
    changeling_name: str,
    path: str,
    auth_store: AuthStoreInterface,
    backend_resolver: BackendResolverInterface,
) -> None:
    name = ChangelingName(changeling_name)

    # Check auth
    if not _check_auth_cookie(cookies=websocket.cookies, changeling_name=name, auth_store=auth_store):
        await websocket.close(code=4003, reason="Not authenticated")
        return

    backend_url = backend_resolver.get_backend_url(name)
    if backend_url is None:
        await websocket.close(code=4004, reason=f"Unknown changeling: {changeling_name}")
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
                    changeling_name=name,
                ),
            )

    except (ConnectionRefusedError, OSError, TimeoutError) as connection_error:
        logger.debug("Backend WebSocket connection failed for {}: {}", changeling_name, connection_error)
        try:
            await websocket.close(code=1011, reason="Backend connection failed")
        except RuntimeError:
            logger.trace("WebSocket already closed when trying to send error for {}", changeling_name)


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
    app.api_route(
        "/agents/{changeling_name}/{path:path}",
        methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"],
    )(_handle_proxy_http)

    # WebSocket route needs manual dependency wiring since Depends doesn't work on WS
    @app.websocket("/agents/{changeling_name}/{path:path}")
    async def proxy_websocket(websocket: WebSocket, changeling_name: str, path: str) -> None:
        await _handle_proxy_websocket(
            websocket=websocket,
            changeling_name=changeling_name,
            path=path,
            auth_store=auth_store,
            backend_resolver=backend_resolver,
        )

    return app
