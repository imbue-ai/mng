import asyncio
import json
import mimetypes
import subprocess
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi import WebSocket
from fastapi import WebSocketDisconnect
from fastapi.responses import Response
from loguru import logger

from imbue.mng_claude_http.primitives import HttpPort


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


def create_app(port: HttpPort, work_dir: str | None = None) -> FastAPI:
    """Create the FastAPI app that bridges browser WebSocket and Claude CLI WebSocket.

    The server:
    1. Serves the React frontend as static files
    2. Accepts browser WebSocket connections at /ws/browser
    3. Accepts Claude CLI WebSocket connections at /ws/cli (via --sdk-url)
    4. Bridges messages between browser and CLI
    """
    # Shared state for the active session
    state: dict[str, Any] = {
        "cli_ws": None,
        "browser_ws": None,
        "cli_process": None,
        "session_id": None,
        "messages": [],
        "metadata": None,
        "is_initialized": False,
    }

    app = FastAPI()

    @app.websocket("/ws/cli")
    async def cli_websocket(websocket: WebSocket) -> None:
        """WebSocket endpoint that Claude CLI connects to via --sdk-url."""
        await websocket.accept()
        state["cli_ws"] = websocket
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
                        state["metadata"] = {
                            "session_id": msg.get("session_id", ""),
                            "model": msg.get("model", ""),
                            "tools": msg.get("tools", []),
                        }
                        state["session_id"] = msg.get("session_id", "")
                        state["is_initialized"] = True

                    # Store assistant messages for history
                    if msg_type == "assistant":
                        state["messages"].append(msg)

                    # Forward to browser if connected
                    browser_ws = state.get("browser_ws")
                    if browser_ws is not None:
                        try:
                            await browser_ws.send_text(json.dumps(msg))
                        except Exception:
                            logger.debug("Failed to forward message to browser")
                            state["browser_ws"] = None

        except WebSocketDisconnect:
            logger.info("Claude CLI disconnected")
        except Exception as e:
            logger.error("CLI WebSocket error: {}", e)
        finally:
            state["cli_ws"] = None

    @app.websocket("/ws/browser")
    async def browser_websocket(websocket: WebSocket) -> None:
        """WebSocket endpoint for browser connections."""
        await websocket.accept()
        state["browser_ws"] = websocket
        logger.info("Browser connected via WebSocket")

        try:
            # Send current state to newly connected browser
            init_msg = {
                "type": "connection_state",
                "cli_connected": state["cli_ws"] is not None,
                "metadata": state["metadata"],
                "messages": state["messages"],
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

                if msg_type == "start_session":
                    # Browser requests to start a new Claude session
                    prompt = msg.get("prompt", "")
                    model = msg.get("model")
                    await _start_claude_session(state, port, prompt, model, work_dir)

                elif msg_type == "send_message":
                    # Browser sends a follow-up message to active session
                    cli_ws = state.get("cli_ws")
                    if cli_ws is not None:
                        user_msg = {
                            "type": "user",
                            "message": {
                                "role": "user",
                                "content": msg.get("content", ""),
                            },
                            "session_id": state.get("session_id", ""),
                            "uuid": str(uuid.uuid4()),
                        }
                        try:
                            await cli_ws.send_text(json.dumps(user_msg))
                        except Exception:
                            logger.error("Failed to send message to CLI")

                elif msg_type == "tool_response":
                    # Browser sends a tool approval/denial
                    cli_ws = state.get("cli_ws")
                    if cli_ws is not None:
                        try:
                            await cli_ws.send_text(json.dumps(msg.get("response", {})))
                        except Exception:
                            logger.error("Failed to send tool response to CLI")

                elif msg_type == "interrupt":
                    # Browser requests to interrupt the current session
                    cli_ws = state.get("cli_ws")
                    if cli_ws is not None:
                        interrupt_msg = {
                            "type": "control_request",
                            "request_id": str(uuid.uuid4()),
                            "request": {"subtype": "interrupt"},
                        }
                        try:
                            await cli_ws.send_text(json.dumps(interrupt_msg))
                        except Exception:
                            logger.error("Failed to send interrupt to CLI")

        except WebSocketDisconnect:
            logger.info("Browser disconnected")
        except Exception as e:
            logger.error("Browser WebSocket error: {}", e)
        finally:
            state["browser_ws"] = None

    @app.get("/api/status")
    async def get_status() -> dict[str, Any]:
        """Return the current session status."""
        return {
            "cli_connected": state["cli_ws"] is not None,
            "browser_connected": state["browser_ws"] is not None,
            "session_id": state.get("session_id"),
            "is_initialized": state["is_initialized"],
            "message_count": len(state["messages"]),
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

        file_path = frontend_dir / path
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
    state: dict[str, Any],
    port: HttpPort,
    prompt: str,
    model: str | None,
    work_dir: str | None,
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
        "--dangerously-skip-permissions",
    ]

    if model:
        cmd.extend(["--model", model])

    # Add a placeholder prompt (will be replaced by user message via WebSocket)
    cmd.extend(["-p", "placeholder"])

    logger.info("Starting Claude Code: {}", " ".join(cmd))

    # Reset session state
    state["messages"] = []
    state["metadata"] = None
    state["is_initialized"] = False
    state["session_id"] = None

    # Kill existing process if any
    existing = state.get("cli_process")
    if existing is not None and existing.poll() is None:
        existing.terminate()
        try:
            existing.wait(timeout=5)
        except subprocess.TimeoutExpired:
            existing.kill()

    # Start the subprocess
    process = subprocess.Popen(
        cmd,
        cwd=work_dir,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    state["cli_process"] = process

    # Wait for CLI to connect (with timeout)
    for _ in range(50):
        if state.get("cli_ws") is not None:
            break
        await asyncio.sleep(0.1)

    if state.get("cli_ws") is None:
        logger.warning("Claude CLI did not connect within 5 seconds")
        browser_ws = state.get("browser_ws")
        if browser_ws is not None:
            await browser_ws.send_text(
                json.dumps({"type": "error", "error": "Claude CLI failed to connect. Is 'claude' installed?"})
            )
        return

    # Wait for initialization
    for _ in range(50):
        if state.get("is_initialized"):
            break
        await asyncio.sleep(0.1)

    # Send the actual user message
    cli_ws = state.get("cli_ws")
    if cli_ws is not None and prompt:
        user_msg = {
            "type": "user",
            "message": {
                "role": "user",
                "content": prompt,
            },
            "session_id": state.get("session_id", ""),
            "uuid": str(uuid.uuid4()),
        }
        await cli_ws.send_text(json.dumps(user_msg))
        logger.info("Sent initial prompt to Claude CLI")


def run_server(port: HttpPort, work_dir: str | None = None) -> None:
    """Run the server (blocking)."""
    import uvicorn

    app = create_app(port, work_dir)
    uvicorn.run(app, host="127.0.0.1", port=int(port))
