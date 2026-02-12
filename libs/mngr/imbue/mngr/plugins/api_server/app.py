import json
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import Depends
from fastapi import FastAPI
from fastapi import HTTPException
from fastapi import Query
from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.responses import JSONResponse
from fastapi.responses import StreamingResponse
from loguru import logger
from pydantic import SecretStr

from imbue.mngr.plugins.api_server.web_ui import generate_web_ui_html

# The MngrContext and API token are set at startup by the plugin.
_mngr_ctx = None
_api_token: SecretStr | None = None

app = FastAPI(title="mngr API", docs_url=None, redoc_url=None)


def configure_app(mngr_ctx, api_token: SecretStr) -> None:
    """Configure the app with a MngrContext and API token. Called at startup."""
    global _mngr_ctx, _api_token  # noqa: PLW0603
    _mngr_ctx = mngr_ctx
    _api_token = api_token


def _verify_token(request: Request) -> None:
    """Verify the Bearer token in the Authorization header."""
    if _api_token is None:
        raise HTTPException(status_code=500, detail="API server not configured")

    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:]
        if token == _api_token.get_secret_value():
            return

    raise HTTPException(status_code=401, detail="Unauthorized")


def _verify_token_query(token: str = Query(...)) -> None:
    """Verify token passed as a query parameter (for SSE connections)."""
    if _api_token is None:
        raise HTTPException(status_code=500, detail="API server not configured")
    if token != _api_token.get_secret_value():
        raise HTTPException(status_code=401, detail="Unauthorized")


def _get_mngr_ctx():
    if _mngr_ctx is None:
        raise HTTPException(status_code=500, detail="API server not configured")
    return _mngr_ctx


# =========================================================================
# Web UI
# =========================================================================


@app.get("/", response_class=HTMLResponse)
def serve_ui() -> str:
    """Serve the mobile-first web UI."""
    return generate_web_ui_html()


# =========================================================================
# REST API - Agents
# =========================================================================


@app.get("/api/agents", dependencies=[Depends(_verify_token)])
def list_agents_endpoint(
    include: str | None = Query(None, description="CEL filter to include agents"),
    exclude: str | None = Query(None, description="CEL filter to exclude agents"),
) -> JSONResponse:
    """List all agents with their current status."""
    from imbue.mngr.api.list import list_agents as _list_agents

    mngr_ctx = _get_mngr_ctx()
    include_filters = (include,) if include else ()
    exclude_filters = (exclude,) if exclude else ()
    result = _list_agents(
        mngr_ctx=mngr_ctx,
        is_streaming=False,
        include_filters=include_filters,
        exclude_filters=exclude_filters,
    )
    agents_data = [_agent_info_to_dict(a) for a in result.agents]
    return JSONResponse(content={"agents": agents_data, "errors": [e.model_dump() for e in result.errors]})


@app.post("/api/agents/{agent_id}/message", dependencies=[Depends(_verify_token)])
def send_message(agent_id: str, request_body: dict) -> JSONResponse:
    """Send a message to an agent."""
    from imbue.mngr.api.find import find_and_maybe_start_agent_by_name_or_id
    from imbue.mngr.api.list import load_all_agents_grouped_by_host

    mngr_ctx = _get_mngr_ctx()
    message = request_body.get("message", "")
    if not message:
        raise HTTPException(status_code=400, detail="Message is required")

    agents_by_host, _ = load_all_agents_grouped_by_host(mngr_ctx)
    agent, _host = find_and_maybe_start_agent_by_name_or_id(
        agent_id, agents_by_host, mngr_ctx, "api-message", is_start_desired=True,
    )
    agent.send_message(message)
    return JSONResponse(content={"status": "sent"})


@app.post("/api/agents/{agent_id}/stop", dependencies=[Depends(_verify_token)])
def stop_agent(agent_id: str) -> JSONResponse:
    """Stop an agent."""
    from imbue.mngr.api.find import find_and_maybe_start_agent_by_name_or_id
    from imbue.mngr.api.list import load_all_agents_grouped_by_host

    mngr_ctx = _get_mngr_ctx()
    agents_by_host, _ = load_all_agents_grouped_by_host(mngr_ctx)
    agent, host = find_and_maybe_start_agent_by_name_or_id(
        agent_id, agents_by_host, mngr_ctx, "api-stop",
    )
    host.stop_agents([agent.id])
    return JSONResponse(content={"status": "stopped"})


@app.post("/api/agents/{agent_id}/activity", dependencies=[Depends(_verify_token)])
def record_activity(agent_id: str) -> JSONResponse:
    """Record user activity for an agent (heartbeat)."""
    from imbue.mngr.api.find import find_and_maybe_start_agent_by_name_or_id
    from imbue.mngr.api.list import load_all_agents_grouped_by_host
    from imbue.mngr.primitives import ActivitySource

    mngr_ctx = _get_mngr_ctx()
    agents_by_host, _ = load_all_agents_grouped_by_host(mngr_ctx)
    agent, _host = find_and_maybe_start_agent_by_name_or_id(
        agent_id, agents_by_host, mngr_ctx, "api-activity",
    )
    agent.record_activity(ActivitySource.USER)
    return JSONResponse(content={"status": "recorded"})


# =========================================================================
# SSE - Agent Stream (Chunk 7)
# =========================================================================


@app.get("/api/agents/stream", dependencies=[Depends(_verify_token_query)])
async def stream_agents(
    request: Request,
) -> StreamingResponse:
    """SSE endpoint that streams agent list updates.

    Polls the agent list every 5 seconds and pushes changes as SSE events.
    """

    async def event_generator() -> AsyncIterator[str]:
        import asyncio

        from imbue.mngr.api.list import list_agents as _list_agents

        mngr_ctx = _get_mngr_ctx()
        last_snapshot = ""

        while True:
            if await request.is_disconnected():
                break

            try:
                result = _list_agents(mngr_ctx=mngr_ctx, is_streaming=False)
                agents_data = [_agent_info_to_dict(a) for a in result.agents]
                snapshot = json.dumps(agents_data, sort_keys=True, default=str)

                if snapshot != last_snapshot:
                    last_snapshot = snapshot
                    payload = json.dumps({"agents": agents_data}, default=str)
                    yield f"data: {payload}\n\n"
            except Exception:
                logger.debug("Error in SSE agent stream")

            # Poll every 5 seconds, checking for disconnect
            for _ in range(10):
                if await request.is_disconnected():
                    return
                await asyncio.sleep(0.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


# =========================================================================
# Helpers
# =========================================================================


def _agent_info_to_dict(agent_info) -> dict:
    """Convert an AgentInfo to a JSON-serializable dict."""
    data = agent_info.model_dump(mode="json")
    # Ensure host is serializable
    if "host" in data and isinstance(data["host"], dict):
        for key, value in list(data["host"].items()):
            if isinstance(value, Path):
                data["host"][key] = str(value)
    return data
