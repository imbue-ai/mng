import asyncio
import json
import mimetypes
import subprocess
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from typing import Any
from typing import AsyncGenerator

import uvicorn
from fastapi import FastAPI
from fastapi import WebSocket
from fastapi import WebSocketDisconnect
from fastapi.responses import Response
from loguru import logger

from imbue.mng_claude_http.primitives import HttpPort

_DEFAULT_CLI_CONNECT_TIMEOUT_SECONDS: float = 5.0
_CLI_CONNECT_POLL_INTERVAL_SECONDS: float = 0.1


@dataclass
class SessionState:
    """Typed mutable state for the active Claude session."""

    cli_ws: WebSocket | None = None
    browser_ws: WebSocket | None = None
    cli_process: subprocess.Popen[bytes] | None = None
    session_id: str | None = None
    messages: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] | None = None
    is_initialized: bool = False

    def reset(self) -> None:
        """Reset session state for a new session."""
        self.messages = []
        self.metadata = None
        self.is_initialized = False
        self.session_id = None

    def terminate_cli_process(self) -> None:
        """Terminate the CLI subprocess if it is running."""
        if self.cli_process is not None and self.cli_process.poll() is None:
            self.cli_process.terminate()
            try:
                self.cli_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.cli_process.kill()
            self.cli_process = None


def _build_user_message(content: str, session_id: str) -> dict[str, Any]:
    """Build a user message dict for the SDK protocol."""
    return {
        "type": "user",
        "message": {
            "role": "user",
            "content": content,
        },
        "session_id": session_id,
        "uuid": str(uuid.uuid4()),
    }


def _get_frontend_dist_dir() -> Path | None:
    """Find the frontend-dist directory, checking dev and installed locations."""
    possible_paths = [
        # Development: libs/mng_claude_http/frontend-dist
        Path(__file__).parent.parent.parent / "frontend-dist",
        # Installed: share directory (hatch shared-data)
        Path(__file__).parent.parent.parent.parent / "share" / "mng_claude_http" / "frontend-dist",
    ]
    for p in possible_paths:
        if p.exists() and p.is_dir():
            return p
    return None


def create_app(
    port: HttpPort,
    work_dir: Path | None = None,
    cli_connect_timeout: float = _DEFAULT_CLI_CONNECT_TIMEOUT_SECONDS,
) -> FastAPI:
    """Create the FastAPI app that bridges browser WebSocket and Claude CLI WebSocket.

    The server:
    1. Serves the React frontend as static files
    2. Accepts browser WebSocket connections at /ws/browser
    3. Accepts Claude CLI WebSocket connections at /ws/cli (via --sdk-url)
    4. Bridges messages between browser and CLI
    """
    state = SessionState()

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
        yield
        state.terminate_cli_process()

    app = FastAPI(lifespan=lifespan)

    @app.websocket("/ws/cli")
    async def cli_websocket(websocket: WebSocket) -> None:
        """WebSocket endpoint that Claude CLI connects to via --sdk-url."""
        await websocket.accept()
        state.cli_ws = websocket
        logger.info("Claude CLI connected via WebSocket")

        try:
            while True:
                raw = await websocket.receive_text()
                # NDJSON: may contain multiple lines
                for line in raw.strip().split("\n"):
                    if not line.strip():
                        continue
                    try:
                        msg = json.loads(line)
                    except json.JSONDecodeError:
                        logger.warning("Failed to parse CLI message: {}", line[:200])
                        continue

                    msg_type = msg.get("type", "")
                    logger.debug("CLI -> Server: type={}", msg_type)

                    # Store session metadata from init
                    if msg_type == "system" and msg.get("subtype") == "init":
                        state.metadata = {
                            "session_id": msg.get("session_id", ""),
                            "model": msg.get("model", ""),
                            "tools": msg.get("tools", []),
                        }
                        state.session_id = msg.get("session_id", "")
                        state.is_initialized = True

                    # Store assistant messages for history
                    if msg_type == "assistant":
                        state.messages.append(msg)

                    # Forward to browser if connected
                    if state.browser_ws is not None:
                        try:
                            await state.browser_ws.send_text(json.dumps(msg))
                        except WebSocketDisconnect:
                            logger.debug("Browser disconnected while forwarding")
                            state.browser_ws = None

        except WebSocketDisconnect:
            logger.info("Claude CLI disconnected")
        finally:
            state.cli_ws = None

    @app.websocket("/ws/browser")
    async def browser_websocket(websocket: WebSocket) -> None:
        """WebSocket endpoint for browser connections."""
        await websocket.accept()
        state.browser_ws = websocket
        logger.info("Browser connected via WebSocket")

        try:
            # Send current state to newly connected browser
            init_msg = {
                "type": "connection_state",
                "cli_connected": state.cli_ws is not None,
                "metadata": state.metadata,
                "messages": state.messages,
            }
            await websocket.send_text(json.dumps(init_msg))

            while True:
                raw = await websocket.receive_text()
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    logger.warning("Failed to parse browser message: {}", raw[:200])
                    continue

                msg_type = msg.get("type", "")
                logger.debug("Browser -> Server: type={}", msg_type)

                match msg_type:
                    case "start_session":
                        prompt = msg.get("prompt", "")
                        model = msg.get("model")
                        await _start_claude_session(state, port, prompt, model, work_dir, cli_connect_timeout)

                    case "send_message":
                        if state.cli_ws is not None:
                            user_msg = _build_user_message(
                                msg.get("content", ""),
                                state.session_id or "",
                            )
                            try:
                                await state.cli_ws.send_text(json.dumps(user_msg))
                            except WebSocketDisconnect:
                                logger.error("CLI disconnected while sending message")

                    case "tool_response":
                        if state.cli_ws is not None:
                            try:
                                await state.cli_ws.send_text(json.dumps(msg.get("response", {})))
                            except WebSocketDisconnect:
                                logger.error("CLI disconnected while sending tool response")

                    case "interrupt":
                        if state.cli_ws is not None:
                            interrupt_msg = {
                                "type": "control_request",
                                "request_id": str(uuid.uuid4()),
                                "request": {"subtype": "interrupt"},
                            }
                            try:
                                await state.cli_ws.send_text(json.dumps(interrupt_msg))
                            except WebSocketDisconnect:
                                logger.error("CLI disconnected while sending interrupt")

        except WebSocketDisconnect:
            logger.info("Browser disconnected")
        finally:
            state.browser_ws = None

    @app.get("/api/status")
    async def get_status() -> dict[str, Any]:
        """Return the current session status."""
        return {
            "cli_connected": state.cli_ws is not None,
            "browser_connected": state.browser_ws is not None,
            "session_id": state.session_id,
            "is_initialized": state.is_initialized,
            "message_count": len(state.messages),
        }

    @app.get("/{path:path}")
    async def serve_static(path: str = "") -> Response:
        """Serve the pre-built React frontend."""
        if not path:
            path = "index.html"

        frontend_dir = _get_frontend_dist_dir()
        if frontend_dir is None:
            return Response(
                status_code=404,
                content="Frontend not found. Run 'npm run build' in frontend/",
            )

        file_path = (frontend_dir / path).resolve()

        # Validate resolved path stays within frontend directory
        if not file_path.is_relative_to(frontend_dir.resolve()):
            return Response(status_code=403, content="Forbidden")

        if not file_path.exists() or not file_path.is_file():
            # SPA fallback
            file_path = frontend_dir / "index.html"
            if not file_path.exists():
                return Response(status_code=404, content="Not found")

        content = file_path.read_bytes()
        mime_type, _ = mimetypes.guess_type(str(file_path))

        # Inject the WebSocket URL into the HTML
        if file_path.name == "index.html":
            ws_url = f"ws://localhost:{port}/ws/browser"
            content = content.replace(b'"__WS_URL__"', f'"{ws_url}"'.encode())

        return Response(
            content=content,
            media_type=mime_type or "application/octet-stream",
        )

    return app


async def _start_claude_session(
    state: SessionState,
    port: HttpPort,
    prompt: str,
    model: str | None,
    work_dir: Path | None,
    connect_timeout: float = _DEFAULT_CLI_CONNECT_TIMEOUT_SECONDS,
) -> None:
    """Start a Claude Code subprocess with --sdk-url pointing to our server."""
    sdk_url = f"ws://localhost:{port}/ws/cli"

    cmd = [
        "claude",
        "--sdk-url",
        sdk_url,
        "--print",
        "--output-format",
        "stream-json",
        "--input-format",
        "stream-json",
        "--verbose",
    ]

    if model:
        cmd.extend(["--model", model])

    # Add a placeholder prompt (will be replaced by user message via WebSocket)
    cmd.extend(["-p", "placeholder"])

    logger.info("Starting Claude Code: {}", " ".join(cmd))

    # Reset session state and terminate any existing process
    state.reset()
    state.terminate_cli_process()

    # Start the subprocess
    try:
        process = subprocess.Popen(
            cmd,
            cwd=str(work_dir) if work_dir else None,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        logger.error("'claude' command not found. Is Claude Code installed?")
        if state.browser_ws is not None:
            await state.browser_ws.send_text(
                json.dumps({"type": "error", "error": "'claude' command not found. Is Claude Code installed?"})
            )
        return
    state.cli_process = process

    # Wait for CLI to connect (with timeout)
    poll_count = int(connect_timeout / _CLI_CONNECT_POLL_INTERVAL_SECONDS)
    for _ in range(poll_count):
        if state.cli_ws is not None:
            break
        await asyncio.sleep(_CLI_CONNECT_POLL_INTERVAL_SECONDS)

    if state.cli_ws is None:
        logger.warning("Claude CLI did not connect within {} seconds", connect_timeout)
        if state.browser_ws is not None:
            await state.browser_ws.send_text(
                json.dumps({"type": "error", "error": "Claude CLI failed to connect. Is 'claude' installed?"})
            )
        return

    # Wait for initialization
    for _ in range(50):
        if state.is_initialized:
            break
        await asyncio.sleep(0.1)

    # Send the actual user message
    if state.cli_ws is not None and prompt:
        user_msg = _build_user_message(prompt, state.session_id or "")
        await state.cli_ws.send_text(json.dumps(user_msg))
        logger.info("Sent initial prompt to Claude CLI")


def run_server(port: HttpPort, work_dir: Path | None = None) -> None:
    """Run the server (blocking)."""
    app = create_app(port, work_dir)
    uvicorn.run(app, host="127.0.0.1", port=int(port))
