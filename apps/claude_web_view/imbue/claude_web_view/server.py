"""FastAPI server serving frontend + SSE endpoint."""

import asyncio
import json
import mimetypes
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi import Request
from fastapi.responses import Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .parser import TranscriptParser
from .watcher import TranscriptWatcher


class SendMessageRequest(BaseModel):
    """Request body for sending a message."""

    message: str
    files: list[str] = []  # Base64-encoded image data or file paths


def create_app(transcript_path: Path, theme: str) -> FastAPI:
    """Create FastAPI app with transcript watching."""
    parser = TranscriptParser(transcript_path)
    watcher = TranscriptWatcher(transcript_path, parser)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        await watcher.start()
        yield
        await watcher.stop()

    app = FastAPI(lifespan=lifespan)

    @app.get("/api/sse")
    async def sse_endpoint(request: Request) -> StreamingResponse:
        """Server-Sent Events endpoint for live updates."""

        async def event_generator() -> AsyncGenerator[str, None]:
            # Send initial state
            messages = parser.get_messages()
            metadata = parser.get_metadata()

            init_event = {
                "type": "init",
                "metadata": metadata.model_dump() if metadata else None,
                "messages": [m.model_dump() for m in messages],
            }
            yield f"data: {json.dumps(init_event)}\n\n"

            # Subscribe to updates
            queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
            watcher.subscribe(queue)

            try:
                while True:
                    # Check if client disconnected
                    if await request.is_disconnected():
                        break

                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=30)
                        yield f"data: {json.dumps(event)}\n\n"
                    except asyncio.TimeoutError:
                        # Send keepalive comment
                        yield ": keepalive\n\n"
            except asyncio.CancelledError:
                # Server is shutting down
                pass
            finally:
                watcher.unsubscribe(queue)

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @app.get("/api/config")
    async def get_config() -> dict[str, str]:
        """Return configuration including theme."""
        return {"theme": theme}

    @app.post("/api/send")
    async def send_message(request: SendMessageRequest) -> dict[str, str]:
        """Receive a message from the chat input."""
        print(f"\n{'=' * 60}")
        print("MESSAGE RECEIVED")
        print(f"{'=' * 60}")
        print(f"Message: {request.message}")
        if request.files:
            print(f"Attached files: {len(request.files)}")
            for i, file_data in enumerate(request.files):
                # Show truncated preview of base64 data
                preview = file_data[:50] + "..." if len(file_data) > 50 else file_data
                print(f"  File {i + 1}: {preview}")
        print(f"{'=' * 60}\n")
        return {"status": "received"}

    @app.get("/{path:path}")
    async def serve_static(path: str = "") -> Response:
        """Serve the pre-built React frontend."""
        if not path:
            path = "index.html"

        # Look for frontend-dist in multiple locations
        possible_paths = [
            # Development: apps/claude_web_view/frontend-dist (relative to imbue/claude_web_view/)
            Path(__file__).parent.parent.parent / "frontend-dist" / path,
            # Installed: share directory (hatch shared-data)
            Path(__file__).parent.parent.parent.parent / "share" / "claude_web_view" / "frontend-dist" / path,
        ]

        file_path = None
        for p in possible_paths:
            if p.exists() and p.is_file():
                file_path = p
                break

        # Fall back to index.html for SPA routing
        if file_path is None:
            for p in possible_paths:
                index_path = p.parent / "index.html"
                if index_path.exists():
                    file_path = index_path
                    break

        if file_path is None:
            return Response(status_code=404, content="Frontend not found. Run 'npm run build' in frontend/")

        content = file_path.read_bytes()
        mime_type, _ = mimetypes.guess_type(str(file_path))

        # Inject theme into HTML (only replace the value, not the variable name)
        if file_path.name == "index.html":
            content = content.replace(b'"__INITIAL_THEME__"', f'"{theme}"'.encode())

        return Response(
            content=content,
            media_type=mime_type or "application/octet-stream",
        )

    return app
