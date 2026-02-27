import json

import pytest
from fastapi.testclient import TestClient

from imbue.mng_claude_http.primitives import HttpPort
from imbue.mng_claude_http.server import SessionState
from imbue.mng_claude_http.server import _build_user_message
from imbue.mng_claude_http.server import _get_frontend_dist_dir
from imbue.mng_claude_http.server import create_app


@pytest.fixture()
def client() -> "TestClient":
    """Create a test client for the FastAPI app.

    Uses a short CLI connect timeout so tests that trigger session start
    don't wait the full 5 seconds for a CLI that won't connect.
    """
    fastapi_app = create_app(HttpPort(3457), cli_connect_timeout=0.5)
    return TestClient(fastapi_app)


# --- SessionState tests ---


def test_session_state_has_correct_initial_values() -> None:
    state = SessionState()
    assert state.cli_ws is None
    assert state.browser_ws is None
    assert state.cli_process is None
    assert state.session_id is None
    assert state.messages == []
    assert state.metadata is None
    assert state.is_initialized is False


def test_session_state_reset_clears_session_fields() -> None:
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


def test_session_state_terminate_cli_process_is_safe_when_none() -> None:
    state = SessionState()
    state.terminate_cli_process()


# --- _build_user_message tests ---


def test_build_user_message_creates_correct_structure() -> None:
    msg = _build_user_message("Hello world", "session-123")
    assert msg["type"] == "user"
    assert msg["message"]["role"] == "user"
    assert msg["message"]["content"] == "Hello world"
    assert msg["session_id"] == "session-123"
    assert "uuid" in msg


def test_build_user_message_generates_unique_uuids() -> None:
    msg1 = _build_user_message("Hello", "s1")
    msg2 = _build_user_message("Hello", "s1")
    assert msg1["uuid"] != msg2["uuid"]


# --- Status endpoint tests ---


def test_status_endpoint_returns_initial_state(client: TestClient) -> None:
    response = client.get("/api/status")
    assert response.status_code == 200
    data = response.json()
    assert data["cli_connected"] is False
    assert data["browser_connected"] is False
    assert data["session_id"] is None
    assert data["is_initialized"] is False
    assert data["message_count"] == 0


# --- Static file serving tests ---


def test_serves_index_html_at_root(client: TestClient) -> None:
    frontend_dir = _get_frontend_dist_dir()
    if frontend_dir is None:
        pytest.skip("Frontend not built")
    response = client.get("/")
    assert response.status_code == 200
    assert b"<html" in response.content.lower() or b"<!doctype" in response.content.lower()


def test_serves_index_html_for_spa_routes(client: TestClient) -> None:
    frontend_dir = _get_frontend_dist_dir()
    if frontend_dir is None:
        pytest.skip("Frontend not built")
    response = client.get("/some-route")
    assert response.status_code == 200
    assert b"<html" in response.content.lower() or b"<!doctype" in response.content.lower()


def test_injects_ws_url_into_html(client: TestClient) -> None:
    frontend_dir = _get_frontend_dist_dir()
    if frontend_dir is None:
        pytest.skip("Frontend not built")
    response = client.get("/")
    assert response.status_code == 200
    assert b"ws://localhost:3457/ws/browser" in response.content


# --- Browser WebSocket tests ---


def test_browser_websocket_connects_and_receives_initial_state(client: TestClient) -> None:
    with client.websocket_connect("/ws/browser") as ws:
        raw = ws.receive_text()
        data = json.loads(raw)
        assert data["type"] == "connection_state"
        assert data["cli_connected"] is False
        assert data["metadata"] is None
        assert data["messages"] == []


def test_browser_start_session_without_cli_returns_error(client: TestClient) -> None:
    with client.websocket_connect("/ws/browser") as ws:
        ws.receive_text()
        ws.send_text(
            json.dumps(
                {
                    "type": "start_session",
                    "prompt": "Hello",
                }
            )
        )
        raw = ws.receive_text()
        data = json.loads(raw)
        assert data["type"] == "error"


def test_browser_send_message_without_session_is_silently_ignored(client: TestClient) -> None:
    with client.websocket_connect("/ws/browser") as ws:
        ws.receive_text()
        ws.send_text(
            json.dumps(
                {
                    "type": "send_message",
                    "content": "Hello",
                }
            )
        )


# --- CLI WebSocket tests ---


def test_cli_websocket_accepts_init_message(client: TestClient) -> None:
    with client.websocket_connect("/ws/cli") as ws:
        init_msg = {
            "type": "system",
            "subtype": "init",
            "session_id": "test-session-123",
            "model": "claude-sonnet-4-6",
            "tools": ["Bash", "Read", "Write"],
        }
        ws.send_text(json.dumps(init_msg))


def test_cli_websocket_accepts_assistant_message(client: TestClient) -> None:
    with client.websocket_connect("/ws/cli") as ws:
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


# --- CLI/Browser bridge tests ---


def test_cli_messages_are_stored_and_served_to_browser(client: TestClient) -> None:
    """Verify the CLI->Browser bridge by sending CLI messages first, then
    connecting the browser and checking it receives the stored messages.

    This avoids relying on real-time WebSocket forwarding between two
    concurrent connections, which is timing-dependent under xdist.
    """
    # Step 1: Connect CLI and send init + assistant message
    with client.websocket_connect("/ws/cli") as cli_ws:
        cli_ws.send_text(
            json.dumps(
                {
                    "type": "system",
                    "subtype": "init",
                    "session_id": "bridge-test",
                    "model": "test-model",
                    "tools": ["Bash"],
                }
            )
        )
        cli_ws.send_text(
            json.dumps(
                {
                    "type": "assistant",
                    "message": {
                        "id": "msg_bridge",
                        "type": "message",
                        "role": "assistant",
                        "model": "test-model",
                        "content": [{"type": "text", "text": "Bridge test"}],
                        "stop_reason": "end_turn",
                    },
                    "session_id": "bridge-test",
                }
            )
        )

    # Step 2: Verify state via API -- metadata and messages should be stored
    response = client.get("/api/status")
    data = response.json()
    assert data["is_initialized"] is True
    assert data["message_count"] == 1

    # Step 3: Connect browser and verify it receives the stored state
    with client.websocket_connect("/ws/browser") as browser_ws:
        raw = browser_ws.receive_text()
        state = json.loads(raw)
        assert state["type"] == "connection_state"
        assert state["metadata"] is not None
        assert state["metadata"]["model"] == "test-model"
        assert state["metadata"]["session_id"] == "bridge-test"
        assert len(state["messages"]) == 1
        assert state["messages"][0]["type"] == "assistant"


def test_api_status_reflects_cli_connection_state(client: TestClient) -> None:
    response = client.get("/api/status")
    assert response.json()["cli_connected"] is False

    with client.websocket_connect("/ws/cli"):
        response = client.get("/api/status")
        assert response.json()["cli_connected"] is True


# --- Frontend dist dir tests ---


def test_get_frontend_dist_dir_returns_valid_path_or_none() -> None:
    result = _get_frontend_dist_dir()
    if result is not None:
        assert result.is_dir()
        assert (result / "index.html").exists()
