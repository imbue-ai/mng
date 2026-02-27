import json

import pytest
from fastapi.testclient import TestClient

from imbue.mng_claude_http.primitives import HttpPort
from imbue.mng_claude_http.server import _get_frontend_dist_dir
from imbue.mng_claude_http.server import create_app


@pytest.fixture()
def app() -> "TestClient":
    """Create a test client for the FastAPI app."""
    fastapi_app = create_app(HttpPort(3457))
    return TestClient(fastapi_app)


class TestStatusEndpoint:
    def test_status_returns_initial_state(self, app: TestClient) -> None:
        response = app.get("/api/status")
        assert response.status_code == 200
        data = response.json()
        assert data["cli_connected"] is False
        assert data["browser_connected"] is False
        assert data["session_id"] is None
        assert data["is_initialized"] is False
        assert data["message_count"] == 0


class TestStaticFileServing:
    def test_serves_index_html_at_root(self, app: TestClient) -> None:
        frontend_dir = _get_frontend_dist_dir()
        if frontend_dir is None:
            pytest.skip("Frontend not built")
        response = app.get("/")
        assert response.status_code == 200
        assert b"<html" in response.content.lower() or b"<!doctype" in response.content.lower()

    def test_serves_index_html_for_spa_routes(self, app: TestClient) -> None:
        frontend_dir = _get_frontend_dist_dir()
        if frontend_dir is None:
            pytest.skip("Frontend not built")
        response = app.get("/some-route")
        assert response.status_code == 200
        assert b"<html" in response.content.lower() or b"<!doctype" in response.content.lower()

    def test_injects_ws_url_into_html(self, app: TestClient) -> None:
        frontend_dir = _get_frontend_dist_dir()
        if frontend_dir is None:
            pytest.skip("Frontend not built")
        response = app.get("/")
        assert response.status_code == 200
        # The WS URL should be injected (replacing __WS_URL__)
        assert b"ws://localhost:3457/ws/browser" in response.content


class TestBrowserWebSocket:
    def test_browser_websocket_connects(self, app: TestClient) -> None:
        with app.websocket_connect("/ws/browser") as ws:
            # Should receive initial connection state
            raw = ws.receive_text()
            data = json.loads(raw)
            assert data["type"] == "connection_state"
            assert data["cli_connected"] is False
            assert data["metadata"] is None
            assert data["messages"] == []

    def test_browser_sends_start_session_without_cli(self, app: TestClient) -> None:
        with app.websocket_connect("/ws/browser") as ws:
            # Receive initial state
            ws.receive_text()
            # Send start session -- CLI isn't connected so it will try to spawn
            # and eventually fail, but the message should be accepted
            ws.send_text(
                json.dumps(
                    {
                        "type": "start_session",
                        "prompt": "Hello",
                    }
                )
            )
            # Should get an error since claude isn't installed in test env
            raw = ws.receive_text()
            data = json.loads(raw)
            assert data["type"] == "error"

    def test_browser_sends_message_without_session(self, app: TestClient) -> None:
        with app.websocket_connect("/ws/browser") as ws:
            # Receive initial state
            ws.receive_text()
            # Send a message without active CLI -- should be silently ignored
            ws.send_text(
                json.dumps(
                    {
                        "type": "send_message",
                        "content": "Hello",
                    }
                )
            )
            # No response expected for this case


class TestCliWebSocket:
    def test_cli_websocket_connects(self, app: TestClient) -> None:
        with app.websocket_connect("/ws/cli") as ws:
            # Send an init message like Claude CLI would
            init_msg = {
                "type": "system",
                "subtype": "init",
                "session_id": "test-session-123",
                "model": "claude-sonnet-4-6",
                "tools": ["Bash", "Read", "Write"],
            }
            ws.send_text(json.dumps(init_msg))
            # The server should process the message without error

    def test_cli_sends_assistant_message(self, app: TestClient) -> None:
        with app.websocket_connect("/ws/cli") as ws:
            # Send init
            ws.send_text(
                json.dumps(
                    {
                        "type": "system",
                        "subtype": "init",
                        "session_id": "test-session",
                        "model": "test-model",
                        "tools": [],
                    }
                )
            )

            # Send assistant message
            ws.send_text(
                json.dumps(
                    {
                        "type": "assistant",
                        "message": {
                            "id": "msg_123",
                            "type": "message",
                            "role": "assistant",
                            "model": "test-model",
                            "content": [{"type": "text", "text": "Hello!"}],
                            "stop_reason": "end_turn",
                        },
                        "session_id": "test-session",
                    }
                )
            )
            # The server should store this message


class TestCliBrowserBridge:
    def test_cli_messages_forwarded_to_browser(self, app: TestClient) -> None:
        """When both CLI and browser are connected, CLI messages should be forwarded."""
        # Connect CLI first
        with app.websocket_connect("/ws/cli") as cli_ws:
            # Connect browser
            with app.websocket_connect("/ws/browser") as browser_ws:
                # Browser receives initial state
                raw = browser_ws.receive_text()
                data = json.loads(raw)
                assert data["type"] == "connection_state"
                assert data["cli_connected"] is True  # CLI is already connected

                # CLI sends an init message
                init_msg = {
                    "type": "system",
                    "subtype": "init",
                    "session_id": "bridge-test",
                    "model": "test-model",
                    "tools": ["Bash"],
                }
                cli_ws.send_text(json.dumps(init_msg))

                # Browser should receive the forwarded message
                raw = browser_ws.receive_text()
                forwarded = json.loads(raw)
                assert forwarded["type"] == "system"
                assert forwarded["subtype"] == "init"

    def test_api_status_reflects_connections(self, app: TestClient) -> None:
        # Initially no connections
        response = app.get("/api/status")
        assert response.json()["cli_connected"] is False

        # Connect CLI
        with app.websocket_connect("/ws/cli") as _cli_ws:
            response = app.get("/api/status")
            assert response.json()["cli_connected"] is True


class TestGetFrontendDistDir:
    def test_returns_path_or_none(self) -> None:
        result = _get_frontend_dist_dir()
        # Should return the frontend-dist path since we built it
        if result is not None:
            assert result.is_dir()
            assert (result / "index.html").exists()
