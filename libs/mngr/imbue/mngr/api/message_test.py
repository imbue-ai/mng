import time
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

import pluggy
import pytest

from imbue.mngr.api.create import CreateAgentOptions
from imbue.mngr.api.message import MessageResult
from imbue.mngr.api.message import _agent_to_cel_context
from imbue.mngr.api.message import _send_message_to_agent
from imbue.mngr.api.message import send_message_to_agents
from imbue.mngr.config.data_types import MngrConfig
from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.hosts.host import Host
from imbue.mngr.primitives import AgentId
from imbue.mngr.primitives import AgentLifecycleState
from imbue.mngr.primitives import AgentName
from imbue.mngr.primitives import AgentTypeName
from imbue.mngr.utils.testing import wait_for
from imbue.mngr.primitives import CommandString
from imbue.mngr.primitives import ErrorBehavior
from imbue.mngr.primitives import HostId
from imbue.mngr.primitives import HostName
from imbue.mngr.primitives import ProviderInstanceName
from imbue.mngr.providers.local.instance import LocalProviderInstance


@pytest.fixture
def temp_host_dir(tmp_path: Path) -> Path:
    host_dir = tmp_path / "mngr"
    host_dir.mkdir(parents=True, exist_ok=True)
    return host_dir


@pytest.fixture
def temp_work_dir(tmp_path: Path) -> Path:
    work_dir = tmp_path / "work_dir"
    work_dir.mkdir(parents=True, exist_ok=True)
    return work_dir


@pytest.fixture
def mngr_test_prefix() -> str:
    return f"mngr_{uuid4().hex}-"


def test_message_result_initializes_with_empty_lists() -> None:
    """Test that MessageResult initializes with empty lists."""
    result = MessageResult()
    assert result.successful_agents == []
    assert result.failed_agents == []


def test_message_result_can_add_successful_agent() -> None:
    """Test that we can add successful agents to the result."""
    result = MessageResult()
    result.successful_agents.append("test-agent")
    assert result.successful_agents == ["test-agent"]


def test_message_result_can_add_failed_agent() -> None:
    """Test that we can add failed agents to the result."""
    result = MessageResult()
    result.failed_agents.append(("test-agent", "error message"))
    assert result.failed_agents == [("test-agent", "error message")]


def test_agent_to_cel_context_returns_expected_fields() -> None:
    """Test that _agent_to_cel_context returns the expected fields."""
    mock_agent = MagicMock()
    mock_agent.id = AgentId.generate()
    mock_agent.name = AgentName("test-agent")
    mock_agent.agent_type = AgentTypeName("claude")
    mock_agent.host_id = HostId.generate()
    mock_agent.get_lifecycle_state.return_value = AgentLifecycleState.RUNNING

    context = _agent_to_cel_context(mock_agent, "local")

    assert context["id"] == str(mock_agent.id)
    assert context["name"] == "test-agent"
    assert context["type"] == "claude"
    assert context["state"] == "running"
    assert context["host"]["provider"] == "local"


def test_agent_to_cel_context_handles_stopped_state() -> None:
    """Test that _agent_to_cel_context handles stopped state correctly."""
    mock_agent = MagicMock()
    mock_agent.id = AgentId.generate()
    mock_agent.name = AgentName("stopped-agent")
    mock_agent.agent_type = AgentTypeName("generic")
    mock_agent.host_id = HostId.generate()
    mock_agent.get_lifecycle_state.return_value = AgentLifecycleState.STOPPED

    context = _agent_to_cel_context(mock_agent, "docker")

    assert context["state"] == "stopped"


def test_send_message_to_agents_returns_empty_result_when_no_agents_match(
    temp_host_dir: Path,
    temp_work_dir: Path,
    plugin_manager: pluggy.PluginManager,
    mngr_test_prefix: str,
) -> None:
    """Test that send_message returns empty result when no agents match filters."""
    config = MngrConfig(default_host_dir=temp_host_dir, prefix=mngr_test_prefix)
    mngr_ctx = MngrContext(config=config, pm=plugin_manager)

    result = send_message_to_agents(
        mngr_ctx=mngr_ctx,
        message_content="Hello",
        include_filters=('name == "nonexistent-agent"',),
        all_agents=False,
    )

    assert result.successful_agents == []
    assert result.failed_agents == []


def test_send_message_to_agents_calls_success_callback(
    temp_host_dir: Path,
    temp_work_dir: Path,
    plugin_manager: pluggy.PluginManager,
    mngr_test_prefix: str,
) -> None:
    """Test that send_message calls the success callback when message is sent."""
    config = MngrConfig(default_host_dir=temp_host_dir, prefix=mngr_test_prefix)
    mngr_ctx = MngrContext(config=config, pm=plugin_manager)
    provider = LocalProviderInstance(
        name=ProviderInstanceName("local"),
        host_dir=temp_host_dir,
        mngr_ctx=mngr_ctx,
    )
    host = provider.create_host(HostName("test-message"))
    assert isinstance(host, Host)

    agent = host.create_agent_state(
        work_dir_path=temp_work_dir,
        options=CreateAgentOptions(
            name=AgentName("message-test"),
            agent_type=AgentTypeName("generic"),
            command=CommandString("sleep 847264"),
        ),
    )

    # Start the agent
    host.start_agents([agent.id])

    success_agents: list[str] = []
    error_agents: list[tuple[str, str]] = []

    result = send_message_to_agents(
        mngr_ctx=mngr_ctx,
        message_content="Hello from test",
        all_agents=True,
        on_success=lambda name: success_agents.append(name),
        on_error=lambda name, err: error_agents.append((name, err)),
    )

    # Clean up
    host.destroy_agent(agent)

    assert "message-test" in result.successful_agents
    assert "message-test" in success_agents


def test_send_message_to_agents_fails_for_stopped_agent(
    temp_host_dir: Path,
    temp_work_dir: Path,
    plugin_manager: pluggy.PluginManager,
    mngr_test_prefix: str,
) -> None:
    """Test that sending message to stopped agent fails."""
    config = MngrConfig(default_host_dir=temp_host_dir, prefix=mngr_test_prefix)
    mngr_ctx = MngrContext(config=config, pm=plugin_manager)
    provider = LocalProviderInstance(
        name=ProviderInstanceName("local"),
        host_dir=temp_host_dir,
        mngr_ctx=mngr_ctx,
    )
    host = provider.create_host(HostName("test-stopped"))
    assert isinstance(host, Host)

    agent = host.create_agent_state(
        work_dir_path=temp_work_dir,
        options=CreateAgentOptions(
            name=AgentName("stopped-test"),
            agent_type=AgentTypeName("generic"),
            command=CommandString("sleep 847265"),
        ),
    )

    # Don't start the agent - it should be stopped

    result = send_message_to_agents(
        mngr_ctx=mngr_ctx,
        message_content="Hello",
        all_agents=True,
        error_behavior=ErrorBehavior.CONTINUE,
    )

    # Clean up
    host.destroy_agent(agent)

    # Should have failed because agent has no tmux session
    assert len(result.failed_agents) == 1
    assert result.failed_agents[0][0] == "stopped-test"
    assert "no tmux session" in result.failed_agents[0][1]


def test_send_message_to_replaced_agent_succeeds(
    temp_host_dir: Path,
    temp_work_dir: Path,
    plugin_manager: pluggy.PluginManager,
    mngr_test_prefix: str,
) -> None:
    """Test that _send_message_to_agent succeeds for REPLACED agents."""
    config = MngrConfig(default_host_dir=temp_host_dir, prefix=mngr_test_prefix)
    mngr_ctx = MngrContext(config=config, pm=plugin_manager)
    provider = LocalProviderInstance(
        name=ProviderInstanceName("local"),
        host_dir=temp_host_dir,
        mngr_ctx=mngr_ctx,
    )
    host = provider.create_host(HostName("test-replaced"))
    assert isinstance(host, Host)

    agent = host.create_agent_state(
        work_dir_path=temp_work_dir,
        options=CreateAgentOptions(
            name=AgentName("replaced-test"),
            agent_type=AgentTypeName("generic"),
            command=CommandString("sleep 847268"),
        ),
    )

    # Start the agent
    host.start_agents([agent.id])

    # Mock the agent to return REPLACED state
    mock_agent = MagicMock()
    mock_agent.name = agent.name
    mock_agent.get_lifecycle_state.return_value = AgentLifecycleState.REPLACED
    mock_agent.send_message = agent.send_message

    # Send a unique message
    test_message = f"test_message_{time.time()}"
    result = MessageResult()
    _send_message_to_agent(
        agent=mock_agent,
        message_content=test_message,
        result=result,
        error_behavior=ErrorBehavior.CONTINUE,
        on_success=None,
        on_error=None,
    )

    # Should succeed because tmux session exists even if state is REPLACED
    assert str(agent.name) in result.successful_agents
    assert len(result.failed_agents) == 0

    # Verify the message was actually sent by checking tmux pane content
    # Use wait_for since tmux may not have rendered the message immediately
    session_name = f"{mngr_test_prefix}replaced-test"

    def message_in_pane() -> bool:
        capture_result = host.execute_command(
            f"tmux capture-pane -t '{session_name}' -p",
            timeout_seconds=5.0,
        )
        return capture_result.success and test_message in capture_result.stdout

    wait_for(message_in_pane, timeout=3.0, error_message=f"Message '{test_message}' not found in tmux pane output")

    # Clean up
    host.destroy_agent(agent)


def test_send_message_to_agents_with_include_filter(
    temp_host_dir: Path,
    temp_work_dir: Path,
    plugin_manager: pluggy.PluginManager,
    mngr_test_prefix: str,
) -> None:
    """Test that send_message respects include filters."""
    config = MngrConfig(default_host_dir=temp_host_dir, prefix=mngr_test_prefix)
    mngr_ctx = MngrContext(config=config, pm=plugin_manager)
    provider = LocalProviderInstance(
        name=ProviderInstanceName("local"),
        host_dir=temp_host_dir,
        mngr_ctx=mngr_ctx,
    )
    host = provider.create_host(HostName("test-filter"))
    assert isinstance(host, Host)

    # Create two agents
    agent1 = host.create_agent_state(
        work_dir_path=temp_work_dir,
        options=CreateAgentOptions(
            name=AgentName("filter-test-1"),
            agent_type=AgentTypeName("generic"),
            command=CommandString("sleep 847266"),
        ),
    )
    agent2 = host.create_agent_state(
        work_dir_path=temp_work_dir,
        options=CreateAgentOptions(
            name=AgentName("filter-test-2"),
            agent_type=AgentTypeName("generic"),
            command=CommandString("sleep 847267"),
        ),
    )

    # Start both agents
    host.start_agents([agent1.id, agent2.id])

    # Send message only to agent1 using filter
    result = send_message_to_agents(
        mngr_ctx=mngr_ctx,
        message_content="Hello filtered",
        include_filters=('name == "filter-test-1"',),
        all_agents=False,
    )

    # Clean up
    host.destroy_agent(agent1)
    host.destroy_agent(agent2)

    # Only agent1 should have received the message
    assert "filter-test-1" in result.successful_agents
    assert "filter-test-2" not in result.successful_agents
