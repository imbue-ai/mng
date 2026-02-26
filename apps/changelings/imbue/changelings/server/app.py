import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Final

import httpx
from fastapi import FastAPI
from fastapi import Request
from fastapi import WebSocket
from fastapi import WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.responses import Response
from loguru import logger

from imbue.changelings.primitives import ChangelingName
from imbue.changelings.primitives import OneTimeCode
from imbue.changelings.server.auth import AuthStoreInterface
from imbue.changelings.server.backend_resolver import BackendResolverInterface
from imbue.changelings.server.cookie_manager import create_signed_cookie_value
from imbue.changelings.server.cookie_manager import get_cookie_name_for_changeling
from imbue.changelings.server.cookie_manager import verify_signed_cookie_value
from imbue.changelings.server.proxy import generate_bootstrap_html
from imbue.changelings.server.proxy import generate_service_worker_js
from imbue.changelings.server.proxy import inject_websocket_shim_into_html
from imbue.changelings.server.proxy import rewrite_cookie_path
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


def _get_authenticated_changeling_names(
    request: Request,
    auth_store: AuthStoreInterface,
) -> list[ChangelingName]:
    """Extract changeling names from valid auth cookies in the request."""
    signing_key = auth_store.get_signing_key()
    known_names = auth_store.list_changeling_names_with_valid_codes()
    resolver_names = request.app.state.backend_resolver.list_known_changeling_names()

    all_candidate_names: set[str] = set()
    for name in known_names:
        all_candidate_names.add(str(name))
    for name in resolver_names:
        all_candidate_names.add(str(name))

    authenticated: list[ChangelingName] = []
    for candidate_name_str in sorted(all_candidate_names):
        candidate_name = ChangelingName(candidate_name_str)
        cookie_name = get_cookie_name_for_changeling(candidate_name)
        cookie_value = request.cookies.get(cookie_name)
        if cookie_value is not None:
            verified = verify_signed_cookie_value(
                cookie_value=cookie_value,
                signing_key=signing_key,
            )
            if verified == candidate_name:
                authenticated.append(candidate_name)

    return authenticated


def _is_authenticated_for_changeling(
    request: Request,
    changeling_name: ChangelingName,
    auth_store: AuthStoreInterface,
) -> bool:
    """Check whether the request has a valid auth cookie for the given changeling."""
    signing_key = auth_store.get_signing_key()
    cookie_name = get_cookie_name_for_changeling(changeling_name)
    cookie_value = request.cookies.get(cookie_name)
    if cookie_value is None:
        return False
    verified = verify_signed_cookie_value(
        cookie_value=cookie_value,
        signing_key=signing_key,
    )
    return verified == changeling_name


def _is_websocket_authenticated_for_changeling(
    websocket: WebSocket,
    changeling_name: ChangelingName,
    auth_store: AuthStoreInterface,
) -> bool:
    """Check whether the WebSocket request has a valid auth cookie for the given changeling."""
    signing_key = auth_store.get_signing_key()
    cookie_name = get_cookie_name_for_changeling(changeling_name)
    cookie_value = websocket.cookies.get(cookie_name)
    if cookie_value is None:
        return False
    verified = verify_signed_cookie_value(
        cookie_value=cookie_value,
        signing_key=signing_key,
    )
    return verified == changeling_name


def create_forwarding_server(
    auth_store: AuthStoreInterface,
    backend_resolver: BackendResolverInterface,
    http_client: httpx.AsyncClient | None,
) -> FastAPI:
    """Create the local forwarding server FastAPI application."""
    is_externally_managed_client = http_client is not None

    @asynccontextmanager
    async def _lifespan(inner_app: FastAPI) -> AsyncGenerator[None, None]:
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

    app = FastAPI(lifespan=_lifespan)

    app.state.auth_store = auth_store
    app.state.backend_resolver = backend_resolver
    if http_client is not None:
        app.state.http_client = http_client

    @app.get("/login")
    def login(changeling_name: str, one_time_code: str, request: Request) -> Response:
        name = ChangelingName(changeling_name)
        code = OneTimeCode(one_time_code)

        # If user already has a valid cookie, redirect to landing page
        if _is_authenticated_for_changeling(request=request, changeling_name=name, auth_store=auth_store):
            return Response(status_code=307, headers={"Location": "/"})

        # Render JS redirect to /authenticate (prevents prefetch consumption)
        html = render_login_redirect_page(changeling_name=name, one_time_code=code)
        return HTMLResponse(content=html)

    @app.get("/authenticate")
    def authenticate(changeling_name: str, one_time_code: str) -> Response:
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

    @app.get("/")
    def landing_page(request: Request) -> Response:
        authenticated_names = _get_authenticated_changeling_names(
            request=request,
            auth_store=auth_store,
        )
        html = render_landing_page(accessible_changeling_names=authenticated_names)
        return HTMLResponse(content=html)

    @app.api_route(
        "/agents/{changeling_name}/{path:path}",
        methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"],
    )
    async def proxy_http(changeling_name: str, path: str, request: Request) -> Response:
        name = ChangelingName(changeling_name)

        # Check auth
        if not _is_authenticated_for_changeling(request=request, changeling_name=name, auth_store=auth_store):
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

        # Build proxy URL
        proxy_url = f"{backend_url}/{path}"
        if request.url.query:
            proxy_url += f"?{request.url.query}"

        # Forward headers, dropping host
        headers = dict(request.headers)
        headers.pop("host", None)

        body = await request.body()

        active_http_client: httpx.AsyncClient = app.state.http_client
        resp = await active_http_client.request(
            method=request.method,
            url=proxy_url,
            headers=headers,
            content=body,
        )

        # Build response headers, dropping hop-by-hop headers
        resp_headers: dict[str, list[str]] = {}
        for header_key, header_value in resp.headers.multi_items():
            if header_key.lower() in _EXCLUDED_RESPONSE_HEADERS:
                continue
            if header_key.lower() == "set-cookie":
                header_value = rewrite_cookie_path(
                    set_cookie_header=header_value,
                    changeling_name=name,
                )
            resp_headers.setdefault(header_key, [])
            resp_headers[header_key].append(header_value)

        content: str | bytes = resp.content

        # Inject WebSocket shim into HTML responses
        content_type = resp.headers.get("content-type", "")
        if "text/html" in content_type:
            html_text = resp.text
            injected_html = inject_websocket_shim_into_html(
                html_content=html_text,
                changeling_name=name,
            )
            content = injected_html.encode()

        response = Response(content=content, status_code=resp.status_code)
        for header_key, header_values in resp_headers.items():
            for header_value in header_values:
                response.headers.append(header_key, header_value)
        return response

    @app.websocket("/agents/{changeling_name}/{path:path}")
    async def proxy_websocket(websocket: WebSocket, changeling_name: str, path: str) -> None:
        name = ChangelingName(changeling_name)

        # Check auth
        if not _is_websocket_authenticated_for_changeling(
            websocket=websocket,
            changeling_name=name,
            auth_store=auth_store,
        ):
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

        import websockets

        try:
            async with websockets.connect(ws_url) as backend_ws:

                async def _forward_client_to_backend_raw() -> None:
                    try:
                        data = await websocket.receive()
                        while data:
                            if "text" in data:
                                await backend_ws.send(data["text"])
                            elif "bytes" in data:
                                await backend_ws.send(data["bytes"])
                            else:
                                pass
                            data = await websocket.receive()
                    except WebSocketDisconnect:
                        await backend_ws.close()

                async def _forward_backend_to_client() -> None:
                    try:
                        async for msg in backend_ws:
                            if isinstance(msg, str):
                                await websocket.send_text(msg)
                            else:
                                await websocket.send_bytes(msg)
                    except websockets.exceptions.ConnectionClosed:
                        logger.debug("Backend WebSocket closed for {}", changeling_name)

                await asyncio.gather(
                    _forward_client_to_backend_raw(),
                    _forward_backend_to_client(),
                )

        except (ConnectionRefusedError, OSError, TimeoutError) as connection_error:
            logger.debug("Backend WebSocket connection failed for {}: {}", changeling_name, connection_error)
            try:
                await websocket.close(code=1011, reason="Backend connection failed")
            except RuntimeError:
                logger.trace("WebSocket already closed when trying to send error for {}", changeling_name)

    return app
