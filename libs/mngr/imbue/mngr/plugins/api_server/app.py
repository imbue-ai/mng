import hmac
from pathlib import Path
from typing import Any

from fastapi import Depends
from fastapi import FastAPI
from fastapi import HTTPException
from fastapi import Query
from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.responses import JSONResponse
from loguru import logger
from pydantic import SecretStr
from starlette.responses import Response

from imbue.mngr.api.find import find_and_maybe_start_agent_by_name_or_id
from imbue.mngr.api.list import list_agents as _list_agents
from imbue.mngr.api.list import load_all_agents_grouped_by_host
from imbue.mngr.errors import BaseMngrError
from imbue.mngr.plugins.api_server.web_ui import generate_web_ui_html
from imbue.mngr.primitives import ActivitySource
from imbue.mngr.primitives import ErrorBehavior

_app_state: dict[str, Any] = {"mngr_ctx": None, "api_token": None}

app = FastAPI(title="mngr API", docs_url=None, redoc_url=None)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> Response:
    """Return provider/backend errors as structured JSON instead of raw 500s."""
    logger.error("Unhandled exception in {}: {}", request.url.path, exc)
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc), "error_type": type(exc).__name__},
    )


def configure_app(mngr_ctx: Any, api_token: SecretStr) -> None:
    """Configure the app with a MngrContext and API token. Called at startup."""
    _app_state["mngr_ctx"] = mngr_ctx
    _app_state["api_token"] = api_token


def _verify_token(request: Request) -> None:
    """Verify the Bearer token in the Authorization header."""
    api_token: SecretStr | None = _app_state["api_token"]
    if api_token is None:
        raise HTTPException(status_code=500, detail="API server not configured")

    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:]
        if hmac.compare_digest(token, api_token.get_secret_value()):
            return

    raise HTTPException(status_code=401, detail="Unauthorized")


def _get_mngr_ctx() -> Any:
    if _app_state["mngr_ctx"] is None:
        raise HTTPException(status_code=500, detail="API server not configured")
    return _app_state["mngr_ctx"]


@app.get("/", response_class=HTMLResponse)
def serve_ui() -> str:
    """Serve the mobile-first web UI."""
    return generate_web_ui_html()


@app.get("/api/agents", dependencies=[Depends(_verify_token)])
def list_agents_endpoint(
    include: str | None = Query(None, description="CEL filter to include agents"),
    exclude: str | None = Query(None, description="CEL filter to exclude agents"),
) -> JSONResponse:
    """List all agents with their current status."""
    mngr_ctx = _get_mngr_ctx()
    include_filters = (include,) if include else ()
    exclude_filters = (exclude,) if exclude else ()
    try:
        result = _list_agents(
            mngr_ctx=mngr_ctx,
            is_streaming=False,
            include_filters=include_filters,
            exclude_filters=exclude_filters,
            error_behavior=ErrorBehavior.CONTINUE,
        )
        agents_data = [_agent_info_to_dict(a) for a in result.agents]
        errors = [e.model_dump() for e in result.errors]
    except BaseMngrError as e:
        # Provider initialization failures (e.g. ModalAuthError) can crash before
        # error_behavior takes effect. Return partial results with the error.
        logger.warning("Error loading agents: {}", e)
        agents_data = []
        errors = [{"message": str(e), "error_type": type(e).__name__}]
    return JSONResponse(content={"agents": agents_data, "errors": errors})


@app.post("/api/agents/{agent_id}/message", dependencies=[Depends(_verify_token)])
def send_message(agent_id: str, request_body: dict[str, Any]) -> JSONResponse:
    """Send a message to an agent."""
    mngr_ctx = _get_mngr_ctx()
    message = request_body.get("message", "")
    if not message:
        raise HTTPException(status_code=400, detail="Message is required")

    agents_by_host, _ = load_all_agents_grouped_by_host(mngr_ctx)
    agent, _host = find_and_maybe_start_agent_by_name_or_id(
        agent_id,
        agents_by_host,
        mngr_ctx,
        "api-message",
        is_start_desired=True,
    )
    agent.send_message(message)
    return JSONResponse(content={"status": "sent"})


@app.post("/api/agents/{agent_id}/stop", dependencies=[Depends(_verify_token)])
def stop_agent(agent_id: str) -> JSONResponse:
    """Stop an agent."""
    mngr_ctx = _get_mngr_ctx()
    agents_by_host, _ = load_all_agents_grouped_by_host(mngr_ctx)
    agent, host = find_and_maybe_start_agent_by_name_or_id(
        agent_id,
        agents_by_host,
        mngr_ctx,
        "api-stop",
    )
    host.stop_agents([agent.id])
    return JSONResponse(content={"status": "stopped"})


@app.post("/api/agents/{agent_id}/activity", dependencies=[Depends(_verify_token)])
def record_activity(agent_id: str) -> JSONResponse:
    """Record user activity for an agent (heartbeat)."""
    mngr_ctx = _get_mngr_ctx()
    agents_by_host, _ = load_all_agents_grouped_by_host(mngr_ctx)
    agent, _host = find_and_maybe_start_agent_by_name_or_id(
        agent_id,
        agents_by_host,
        mngr_ctx,
        "api-activity",
    )
    agent.record_activity(ActivitySource.USER)
    return JSONResponse(content={"status": "recorded"})


def _agent_info_to_dict(agent_info: Any) -> dict[str, Any]:
    """Convert an AgentInfo to a JSON-serializable dict."""
    data = agent_info.model_dump(mode="json")
    if "host" in data and isinstance(data["host"], dict):
        for key, value in list(data["host"].items()):
            if isinstance(value, Path):
                data["host"][key] = str(value)
    return data
