import json

import pytest
from fastapi.testclient import TestClient

from imbue.mng_claude_http.primitives import HttpPort
from imbue.mng_claude_http.server import SessionState
from imbue.mng_claude_http.server import _build_user_message
from imbue.mng_claude_http.server import _get_frontend_dist_dir
from imbue.mng_claude_http.server import create_app


@pytest.fixture()
def app() -> "TestClient":
    """Create a test client for the FastAPI app.

    Uses a short CLI connect timeout so tests that trigger session start
    don't wait the full 5 seconds for a CLI that won't connect.
    """
    fastapi_app = create_app(HttpPort(3457), cli_connect_timeout=0.5)
    return TestClient(fastapi_app)


class TestSessionState:
    def test_initial_state(self) -> None:
        state = SessionState()
        assert state.cli_ws is None
        assert state.browser_ws is None
        assert state.cli_process is None
        assert state.session_id is None
        assert state.messages == []
        assert state.metadata is None
        assert state.is_initialized is False

    def test_reset(self) -> None:
        state = SessionState()
        state.session_id = "test-123"
        state.messages = [{"type": "assistant"}]
        state.metadata = {"model": "test"}
        state.is_initialized = True
        state.reset()
        assert state.session_id is None
        assert state.messages == []
        assert state.metadata is None
        assert state.is_initialized is False

    def test_terminate_cli_process_when_none(self) -> None:
        state = SessionState()
        # Should not raise when no process exists
        state.terminate_cli_process()


class TestBuildUserMessage:
    def test_builds_correct_structure(self) -> None:
        msg = _build_user_message("Hello world", "session-123")
        assert msg["type"] == "user"
        assert msg["message"]["role"] == "user"
        assert msg["message"]["content"] == "Hello world"
        assert msg["session_id"] == "session-123"
        assert "uuid" in msg

    def test_unique_uuids(self) -> None:
        msg1 = _build_user_message("Hello", "s1")
        msg2 = _build_user_message("Hello", "s1")
        assert msg1["uuid"] != msg2["uuid"]


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
        assert b"ws://localhost:3457/ws/browser" in response.content


class TestBrowserWebSocket:
    def test_browser_websocket_connects(self, app: TestClient) -> None:
        with app.websocket_connect("/ws/browser") as ws:
            raw = ws.receive_text()
            data = json.loads(raw)
            assert data["type"] == "connection_state"
            assert data["cli_connected"] is False
            assert data["metadata"] is None
            assert data["messages"] == []

    def test_browser_sends_start_session_without_cli(self, app: TestClient) -> None:
        with app.websocket_connect("/ws/browser") as ws:
            ws.receive_text()
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
            ws.receive_text()
            ws.send_text(
                json.dumps(
                    {
                        "type": "send_message",
                        "content": "Hello",
                    }
                )
            )
            # No response expected -- message is silently ignored without CLI


class TestCliWebSocket:
    def test_cli_websocket_connects(self, app: TestClient) -> None:
        with app.websocket_connect("/ws/cli") as ws:
            init_msg = {
                "type": "system",
                "subtype": "init",
                "session_id": "test-session-123",
                "model": "claude-sonnet-4-6",
                "tools": ["Bash", "Read", "Write"],
            }
            ws.send_text(json.dumps(init_msg))

    def test_cli_sends_assistant_message(self, app: TestClient) -> None:
        with app.websocket_connect("/ws/cli") as ws:
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


class TestCliBrowserBridge:
    def test_cli_messages_forwarded_to_browser(self, app: TestClient) -> None:
        """When both CLI and browser are connected, CLI messages should be forwarded."""
        with app.websocket_connect("/ws/cli") as cli_ws:
            with app.websocket_connect("/ws/browser") as browser_ws:
                raw = browser_ws.receive_text()
                data = json.loads(raw)
                assert data["type"] == "connection_state"
                assert data["cli_connected"] is True

                init_msg = {
                    "type": "system",
                    "subtype": "init",
                    "session_id": "bridge-test",
                    "model": "test-model",
                    "tools": ["Bash"],
                }
                cli_ws.send_text(json.dumps(init_msg))

                raw = browser_ws.receive_text()
                forwarded = json.loads(raw)
                assert forwarded["type"] == "system"
                assert forwarded["subtype"] == "init"

    def test_api_status_reflects_connections(self, app: TestClient) -> None:
        response = app.get("/api/status")
        assert response.json()["cli_connected"] is False

        with app.websocket_connect("/ws/cli"):
            response = app.get("/api/status")
            assert response.json()["cli_connected"] is True


class TestGetFrontendDistDir:
    def test_returns_path_or_none(self) -> None:
        result = _get_frontend_dist_dir()
        if result is not None:
            assert result.is_dir()
            assert (result / "index.html").exists()
