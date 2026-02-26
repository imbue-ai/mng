#!/usr/bin/env python3
"""Demo script that starts test backend servers and the forwarding server.

This demonstrates the full flow:
1. Starts two simple HTTP backends on separate ports
2. Sets up the forwarding server with auth codes for both
3. Prints login URLs for each backend
4. Starts the forwarding server

Usage:
    uv run python apps/changelings/scripts/demo_forwarding_server.py
"""

import secrets
import tempfile
import threading
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from imbue.changelings.primitives import ChangelingName
from imbue.changelings.primitives import OneTimeCode
from imbue.changelings.server.app import create_forwarding_server
from imbue.changelings.server.auth import FileAuthStore
from imbue.changelings.server.backend_resolver import StaticBackendResolver


def _create_demo_backend(agent_name: str, port: int) -> FastAPI:
    """Create a simple demo backend for testing."""
    app = FastAPI()

    @app.get("/")
    def root() -> HTMLResponse:
        return HTMLResponse(f"""<!DOCTYPE html>
<html>
<head><title>{agent_name}</title></head>
<body style="font-family: system-ui; padding: 40px;">
  <h1>Hello from {agent_name}!</h1>
  <p>This is running on port {port}.</p>
  <p>Current path: <code id="path"></code></p>
  <script>document.getElementById('path').textContent = window.location.pathname;</script>
</body>
</html>""")

    @app.get("/api/status")
    def status() -> dict[str, str]:
        return {"agent": agent_name, "status": "running", "port": str(port)}

    return app


def _run_backend(app: FastAPI, port: int) -> None:
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


def main() -> None:
    # Configuration
    forwarding_port = 8420
    backend_configs = [
        ("elena-turing", 9001),
        ("code-reviewer", 9002),
    ]

    # Create temp dir for auth data
    data_dir = Path(tempfile.mkdtemp(prefix="changelings-demo-"))
    auth_store = FileAuthStore(data_directory=data_dir / "auth")

    # Start backend servers in threads
    url_by_name: dict[str, str] = {}
    for agent_name, port in backend_configs:
        backend_app = _create_demo_backend(agent_name=agent_name, port=port)
        thread = threading.Thread(
            target=_run_backend,
            args=(backend_app, port),
            daemon=True,
        )
        thread.start()
        url_by_name[agent_name] = f"http://127.0.0.1:{port}"

    # Create backend resolver
    backend_resolver = StaticBackendResolver(url_by_changeling_name=url_by_name)

    # Generate one-time codes and print login URLs
    print()
    print("=" * 60)
    print("Changelings Forwarding Server Demo")
    print("=" * 60)
    print()
    print(f"Data directory: {data_dir}")
    print()

    for agent_name, _ in backend_configs:
        code = OneTimeCode(secrets.token_urlsafe(32))
        auth_store.add_one_time_code(
            changeling_name=ChangelingName(agent_name),
            code=code,
        )
        login_url = f"http://127.0.0.1:{forwarding_port}/login?changeling_name={agent_name}&one_time_code={code}"
        print(f"Login URL for {agent_name}:")
        print(f"  {login_url}")
        print()

    print(f"Landing page: http://127.0.0.1:{forwarding_port}/")
    print()
    print("Instructions:")
    print("  1. Open a login URL in your browser to authenticate")
    print("  2. You will be redirected to the agent's proxied page")
    print("  3. Visit the landing page to see all authenticated agents")
    print()
    print("Press Ctrl+C to stop.")
    print("=" * 60)
    print()

    # Start forwarding server
    app = create_forwarding_server(
        auth_store=auth_store,
        backend_resolver=backend_resolver,
        http_client=None,
    )
    uvicorn.run(app, host="127.0.0.1", port=forwarding_port)


if __name__ == "__main__":
    main()
