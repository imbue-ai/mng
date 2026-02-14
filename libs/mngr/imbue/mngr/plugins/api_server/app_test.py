"""Unit tests for the API server FastAPI application."""

from fastapi.testclient import TestClient
from pydantic import SecretStr

from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.plugins.api_server.app import app
from imbue.mngr.plugins.api_server.app import configure_app

TEST_TOKEN = SecretStr("test-api-token-12345")
AUTH_HEADER = {"Authorization": f"Bearer {TEST_TOKEN.get_secret_value()}"}


def _create_api_client(mngr_ctx: MngrContext) -> TestClient:
    configure_app(mngr_ctx=mngr_ctx, api_token=TEST_TOKEN)
    return TestClient(app)


def test_web_ui_serves_html(temp_mngr_ctx: MngrContext) -> None:
    """The root endpoint returns the web UI HTML without auth."""
    client = _create_api_client(temp_mngr_ctx)
    response = client.get("/")
    assert response.status_code == 200
    assert "<!DOCTYPE html>" in response.text
    assert "mngr" in response.text.lower()


def test_list_agents_requires_auth(temp_mngr_ctx: MngrContext) -> None:
    """The /api/agents endpoint returns 401 without a token."""
    client = _create_api_client(temp_mngr_ctx)
    response = client.get("/api/agents")
    assert response.status_code == 401


def test_list_agents_rejects_wrong_token(temp_mngr_ctx: MngrContext) -> None:
    """The /api/agents endpoint returns 401 with an incorrect token."""
    client = _create_api_client(temp_mngr_ctx)
    response = client.get("/api/agents", headers={"Authorization": "Bearer wrong-token"})
    assert response.status_code == 401


def test_list_agents_empty(temp_mngr_ctx: MngrContext) -> None:
    """The /api/agents endpoint returns empty list when no agents exist."""
    client = _create_api_client(temp_mngr_ctx)
    response = client.get("/api/agents", headers=AUTH_HEADER)
    assert response.status_code == 200
    data = response.json()
    assert data["agents"] == []
    assert data["errors"] == []


def test_send_message_requires_body(temp_mngr_ctx: MngrContext) -> None:
    """The /api/agents/{id}/message endpoint returns 400 when message is empty."""
    client = _create_api_client(temp_mngr_ctx)
    response = client.post(
        "/api/agents/fake-id/message",
        headers=AUTH_HEADER,
        json={"message": ""},
    )
    assert response.status_code == 400
    assert "Message is required" in response.json()["detail"]
