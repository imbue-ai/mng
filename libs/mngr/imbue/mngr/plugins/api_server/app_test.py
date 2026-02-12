"""Unit tests for the API server FastAPI application."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.hosts.host import Host
from imbue.mngr.interfaces.host import CreateAgentOptions
from imbue.mngr.plugins.api_server.app import app
from imbue.mngr.plugins.api_server.app import configure_app
from imbue.mngr.primitives import AgentName
from imbue.mngr.primitives import AgentTypeName
from imbue.mngr.primitives import CommandString
from imbue.mngr.primitives import HostName
from imbue.mngr.providers.local.instance import LocalProviderInstance

TEST_TOKEN = SecretStr("test-api-token-12345")
AUTH_HEADER = {"Authorization": f"Bearer {TEST_TOKEN.get_secret_value()}"}


@pytest.fixture
def api_client(temp_mngr_ctx: MngrContext) -> TestClient:
    """Create a FastAPI TestClient configured with a test MngrContext."""
    configure_app(mngr_ctx=temp_mngr_ctx, api_token=TEST_TOKEN)
    return TestClient(app)


def test_web_ui_serves_html(api_client: TestClient) -> None:
    """The root endpoint returns the web UI HTML without auth."""
    response = api_client.get("/")
    assert response.status_code == 200
    assert "<!DOCTYPE html>" in response.text
    assert "mngr" in response.text.lower()


def test_list_agents_requires_auth(api_client: TestClient) -> None:
    """The /api/agents endpoint returns 401 without a token."""
    response = api_client.get("/api/agents")
    assert response.status_code == 401


def test_list_agents_rejects_wrong_token(api_client: TestClient) -> None:
    """The /api/agents endpoint returns 401 with an incorrect token."""
    response = api_client.get("/api/agents", headers={"Authorization": "Bearer wrong-token"})
    assert response.status_code == 401


def test_list_agents_empty(api_client: TestClient) -> None:
    """The /api/agents endpoint returns empty list when no agents exist."""
    response = api_client.get("/api/agents", headers=AUTH_HEADER)
    assert response.status_code == 200
    data = response.json()
    assert data["agents"] == []
    assert data["errors"] == []


def test_list_agents_with_agent(
    api_client: TestClient,
    local_provider: LocalProviderInstance,
    temp_work_dir: Path,
) -> None:
    """The /api/agents endpoint returns agents that exist."""
    host = local_provider.create_host(HostName("test-api-list"))
    assert isinstance(host, Host)

    agent = host.create_agent_state(
        work_dir_path=temp_work_dir,
        options=CreateAgentOptions(
            name=AgentName("api-test-agent"),
            agent_type=AgentTypeName("generic"),
            command=CommandString("sleep 847291"),
        ),
    )
    host.start_agents([agent.id])

    try:
        response = api_client.get("/api/agents", headers=AUTH_HEADER)
        assert response.status_code == 200
        data = response.json()
        assert len(data["agents"]) >= 1
        agent_names = [a["name"] for a in data["agents"]]
        assert "api-test-agent" in agent_names
    finally:
        host.stop_agents([agent.id])
        host.destroy_agent(agent)


def test_send_message_requires_body(api_client: TestClient) -> None:
    """The /api/agents/{id}/message endpoint returns 400 when message is empty."""
    response = api_client.post(
        "/api/agents/fake-id/message",
        headers=AUTH_HEADER,
        json={"message": ""},
    )
    assert response.status_code == 400
    assert "Message is required" in response.json()["detail"]


def test_send_message_to_agent(
    api_client: TestClient,
    local_provider: LocalProviderInstance,
    temp_work_dir: Path,
) -> None:
    """The /api/agents/{id}/message endpoint sends a message to a running agent."""
    host = local_provider.create_host(HostName("test-api-msg"))
    assert isinstance(host, Host)

    agent = host.create_agent_state(
        work_dir_path=temp_work_dir,
        options=CreateAgentOptions(
            name=AgentName("api-msg-agent"),
            agent_type=AgentTypeName("generic"),
            command=CommandString("sleep 847292"),
        ),
    )
    host.start_agents([agent.id])

    try:
        response = api_client.post(
            f"/api/agents/{agent.id}/message",
            headers=AUTH_HEADER,
            json={"message": "hello from test"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "sent"
    finally:
        host.stop_agents([agent.id])
        host.destroy_agent(agent)


def test_stop_agent_endpoint(
    api_client: TestClient,
    local_provider: LocalProviderInstance,
    temp_work_dir: Path,
) -> None:
    """The /api/agents/{id}/stop endpoint stops a running agent."""
    host = local_provider.create_host(HostName("test-api-stop"))
    assert isinstance(host, Host)

    agent = host.create_agent_state(
        work_dir_path=temp_work_dir,
        options=CreateAgentOptions(
            name=AgentName("api-stop-agent"),
            agent_type=AgentTypeName("generic"),
            command=CommandString("sleep 847293"),
        ),
    )
    host.start_agents([agent.id])

    try:
        response = api_client.post(
            f"/api/agents/{agent.id}/stop",
            headers=AUTH_HEADER,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "stopped"
    finally:
        host.destroy_agent(agent)


def test_sse_stream_requires_query_token(api_client: TestClient) -> None:
    """The SSE endpoint requires a token query parameter."""
    response = api_client.get("/api/agents/stream")
    assert response.status_code == 422  # Missing required query param


def test_sse_stream_rejects_wrong_token(api_client: TestClient) -> None:
    """The SSE endpoint rejects an incorrect token."""
    response = api_client.get("/api/agents/stream?token=wrong")
    assert response.status_code == 401


