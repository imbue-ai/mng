"""Integration tests for the API server.

Tests the full request lifecycle through the API server endpoints with real
agents, hosts, and provider instances -- no mocks.
"""

from pathlib import Path

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

TEST_TOKEN = SecretStr("integration-test-token-abc123")
AUTH = {"Authorization": f"Bearer {TEST_TOKEN.get_secret_value()}"}


def _create_configured_client(mngr_ctx: MngrContext) -> TestClient:
    configure_app(mngr_ctx=mngr_ctx, api_token=TEST_TOKEN)
    return TestClient(app)


def test_full_agent_lifecycle_via_api(
    temp_mngr_ctx: MngrContext,
    local_provider: LocalProviderInstance,
    temp_work_dir: Path,
) -> None:
    """Test the complete agent lifecycle: create, list, message, stop, list again."""
    client = _create_configured_client(temp_mngr_ctx)

    host = local_provider.create_host(HostName("test-lifecycle"))
    assert isinstance(host, Host)

    agent = host.create_agent_state(
        work_dir_path=temp_work_dir,
        options=CreateAgentOptions(
            name=AgentName("lifecycle-agent"),
            agent_type=AgentTypeName("generic"),
            command=CommandString("sleep 847301"),
        ),
    )
    host.start_agents([agent.id])

    try:
        # List agents -- should include our agent
        response = client.get("/api/agents", headers=AUTH)
        assert response.status_code == 200
        data = response.json()
        assert any(a["name"] == "lifecycle-agent" for a in data["agents"])

        # Send a message
        response = client.post(
            f"/api/agents/{agent.id}/message",
            headers=AUTH,
            json={"message": "hello lifecycle"},
        )
        assert response.status_code == 200

        # Record activity
        response = client.post(
            f"/api/agents/{agent.id}/activity",
            headers=AUTH,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "recorded"

        # Stop via API
        response = client.post(
            f"/api/agents/{agent.id}/stop",
            headers=AUTH,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "stopped"
    finally:
        host.destroy_agent(agent)


def test_list_agents_with_cel_filters(
    temp_mngr_ctx: MngrContext,
    local_provider: LocalProviderInstance,
    temp_work_dir: Path,
) -> None:
    """Test the CEL include/exclude filter query parameters on list agents."""
    client = _create_configured_client(temp_mngr_ctx)

    host = local_provider.create_host(HostName("test-filters"))
    assert isinstance(host, Host)

    agent = host.create_agent_state(
        work_dir_path=temp_work_dir,
        options=CreateAgentOptions(
            name=AgentName("filter-test-agent"),
            agent_type=AgentTypeName("generic"),
            command=CommandString("sleep 847302"),
        ),
    )
    host.start_agents([agent.id])

    try:
        # Include filter matching the agent name
        response = client.get(
            "/api/agents",
            headers=AUTH,
            params={"include": 'name == "filter-test-agent"'},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["agents"]) == 1
        assert data["agents"][0]["name"] == "filter-test-agent"

        # Exclude filter removing the agent
        response = client.get(
            "/api/agents",
            headers=AUTH,
            params={"exclude": 'name == "filter-test-agent"'},
        )
        assert response.status_code == 200
        data = response.json()
        assert not any(a["name"] == "filter-test-agent" for a in data["agents"])
    finally:
        host.stop_agents([agent.id])
        host.destroy_agent(agent)


def test_web_ui_contains_polling_script(temp_mngr_ctx: MngrContext) -> None:
    """The web UI HTML includes the polling-based refresh mechanism."""
    client = _create_configured_client(temp_mngr_ctx)
    response = client.get("/")
    assert response.status_code == 200
    assert "setInterval" in response.text
    assert "refreshAgents" in response.text
    # Verify no SSE references remain
    assert "EventSource" not in response.text
    assert "/api/agents/stream" not in response.text


def test_api_agent_info_includes_host_details(
    temp_mngr_ctx: MngrContext,
    local_provider: LocalProviderInstance,
    temp_work_dir: Path,
) -> None:
    """Agent info returned by the API includes host details."""
    client = _create_configured_client(temp_mngr_ctx)

    host = local_provider.create_host(HostName("test-host-details"))
    assert isinstance(host, Host)

    agent = host.create_agent_state(
        work_dir_path=temp_work_dir,
        options=CreateAgentOptions(
            name=AgentName("host-detail-agent"),
            agent_type=AgentTypeName("generic"),
            command=CommandString("sleep 847303"),
        ),
    )
    host.start_agents([agent.id])

    try:
        response = client.get("/api/agents", headers=AUTH)
        assert response.status_code == 200
        data = response.json()
        agent_data = next(a for a in data["agents"] if a["name"] == "host-detail-agent")
        assert "host" in agent_data
        assert "provider_name" in agent_data["host"]
        assert agent_data["host"]["provider_name"] == "local"
    finally:
        host.stop_agents([agent.id])
        host.destroy_agent(agent)
