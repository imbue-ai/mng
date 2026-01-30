"""Tests for error handling in message.py.

These tests focus on error handling paths that require specific error conditions,
including provider not found, agent not found, stopped agents, and MngrError handling.
"""

from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pluggy
import pytest

from imbue.mngr.api.create import CreateAgentOptions
from imbue.mngr.api.message import send_message_to_agents
from imbue.mngr.config.data_types import MngrConfig
from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.errors import MngrError
from imbue.mngr.errors import ProviderInstanceNotFoundError
from imbue.mngr.hosts.host import Host
from imbue.mngr.primitives import AgentId
from imbue.mngr.primitives import AgentName
from imbue.mngr.primitives import AgentReference
from imbue.mngr.primitives import AgentTypeName
from imbue.mngr.primitives import CommandString
from imbue.mngr.primitives import ErrorBehavior
from imbue.mngr.primitives import HostId
from imbue.mngr.primitives import HostName
from imbue.mngr.primitives import HostReference
from imbue.mngr.primitives import ProviderInstanceName
from imbue.mngr.providers.local.instance import LocalProviderInstance


@pytest.fixture
def mngr_test_prefix() -> str:
    return f"mngr_{uuid4().hex}-"


def test_provider_not_found_with_abort_raises_exception(
    temp_host_dir: Path,
    plugin_manager: pluggy.PluginManager,
    mngr_test_prefix: str,
) -> None:
    """Test that ProviderInstanceNotFoundError is raised when provider not found with ABORT behavior."""
    config = MngrConfig(default_host_dir=temp_host_dir, prefix=mngr_test_prefix)
    mngr_ctx = MngrContext(config=config, pm=plugin_manager)

    # Create a fake host reference with a non-existent provider
    fake_host_ref = HostReference(
        host_id=HostId.generate(),
        host_name=HostName("fake-host"),
        provider_name=ProviderInstanceName("nonexistent_provider"),
    )

    # Create fake agent reference
    fake_agent_ref = AgentReference(
        host_id=fake_host_ref.host_id,
        agent_id=AgentId.generate(),
        agent_name=AgentName("fake-agent"),
        provider_name=fake_host_ref.provider_name,
    )

    # Mock load_all_agents_grouped_by_host to return our fake data
    with patch("imbue.mngr.api.message.load_all_agents_grouped_by_host") as mock_load:
        mock_load.return_value = {fake_host_ref: [fake_agent_ref]}

        with pytest.raises(ProviderInstanceNotFoundError) as exc_info:
            send_message_to_agents(
                mngr_ctx=mngr_ctx,
                message_content="Hello",
                all_agents=True,
                error_behavior=ErrorBehavior.ABORT,
            )

        assert exc_info.value.provider_name == ProviderInstanceName("nonexistent_provider")


def test_provider_not_found_with_continue_skips_host(
    temp_host_dir: Path,
    plugin_manager: pluggy.PluginManager,
    mngr_test_prefix: str,
) -> None:
    """Test that missing provider is skipped with CONTINUE behavior (does not raise)."""
    config = MngrConfig(default_host_dir=temp_host_dir, prefix=mngr_test_prefix)
    mngr_ctx = MngrContext(config=config, pm=plugin_manager)

    fake_host_ref = HostReference(
        host_id=HostId.generate(),
        host_name=HostName("fake-host"),
        provider_name=ProviderInstanceName("nonexistent_provider"),
    )

    fake_agent_ref = AgentReference(
        host_id=fake_host_ref.host_id,
        agent_id=AgentId.generate(),
        agent_name=AgentName("fake-agent"),
        provider_name=fake_host_ref.provider_name,
    )

    with patch("imbue.mngr.api.message.load_all_agents_grouped_by_host") as mock_load:
        mock_load.return_value = {fake_host_ref: [fake_agent_ref]}

        # Should not raise, just skip the host
        result = send_message_to_agents(
            mngr_ctx=mngr_ctx,
            message_content="Hello",
            all_agents=True,
            error_behavior=ErrorBehavior.CONTINUE,
        )

        # No successful agents, but also no failed agents (provider skip doesn't add to failed)
        assert result.successful_agents == []
        assert result.failed_agents == []


def test_agent_not_found_on_host_with_continue_records_error_and_calls_callback(
    temp_host_dir: Path,
    temp_work_dir: Path,
    plugin_manager: pluggy.PluginManager,
    mngr_test_prefix: str,
) -> None:
    """Test that agent not found on host records error and invokes on_error callback."""
    config = MngrConfig(default_host_dir=temp_host_dir, prefix=mngr_test_prefix)
    mngr_ctx = MngrContext(config=config, pm=plugin_manager)
    provider = LocalProviderInstance(
        name=ProviderInstanceName("local"),
        host_dir=temp_host_dir,
        mngr_ctx=mngr_ctx,
    )
    host = provider.create_host(HostName("test-agent-not-found"))
    assert isinstance(host, Host)

    # Create a host reference pointing to a real host
    host_ref = HostReference(
        host_id=host.id,
        host_name=HostName(host.connector.name),
        provider_name=ProviderInstanceName("local"),
    )

    # Create a fake agent reference with an ID that doesn't exist on the host
    # (this agent_id is freshly generated so won't match any existing agent)
    fake_agent_ref = AgentReference(
        host_id=host_ref.host_id,
        agent_id=AgentId.generate(),
        agent_name=AgentName("ghost-agent"),
        provider_name=host_ref.provider_name,
    )

    error_callback_calls: list[tuple[str, str]] = []

    with patch("imbue.mngr.api.message.load_all_agents_grouped_by_host") as mock_load:
        mock_load.return_value = {host_ref: [fake_agent_ref]}

        result = send_message_to_agents(
            mngr_ctx=mngr_ctx,
            message_content="Hello",
            all_agents=True,
            error_behavior=ErrorBehavior.CONTINUE,
            on_error=lambda name, err: error_callback_calls.append((name, err)),
        )

    # Should have one failed agent
    assert len(result.failed_agents) == 1
    assert result.failed_agents[0][0] == "ghost-agent"
    assert "not found on host" in result.failed_agents[0][1]

    # on_error callback should have been called
    assert len(error_callback_calls) == 1
    assert error_callback_calls[0][0] == "ghost-agent"
    assert "not found on host" in error_callback_calls[0][1]


def test_stopped_agent_with_abort_raises_mngr_error(
    temp_host_dir: Path,
    temp_work_dir: Path,
    plugin_manager: pluggy.PluginManager,
    mngr_test_prefix: str,
) -> None:
    """Test that sending message to stopped agent with ABORT raises MngrError."""

    config = MngrConfig(default_host_dir=temp_host_dir, prefix=mngr_test_prefix)
    mngr_ctx = MngrContext(config=config, pm=plugin_manager)
    provider = LocalProviderInstance(
        name=ProviderInstanceName("local"),
        host_dir=temp_host_dir,
        mngr_ctx=mngr_ctx,
    )
    host = provider.create_host(HostName("test-stopped-abort"))
    assert isinstance(host, Host)

    agent = host.create_agent_state(
        work_dir_path=temp_work_dir,
        options=CreateAgentOptions(
            name=AgentName("stopped-abort-test"),
            agent_type=AgentTypeName("generic"),
            command=CommandString("sleep 847268"),
        ),
    )

    # Don't start the agent - it should be stopped

    with pytest.raises(MngrError) as exc_info:
        send_message_to_agents(
            mngr_ctx=mngr_ctx,
            message_content="Hello",
            all_agents=True,
            error_behavior=ErrorBehavior.ABORT,
        )

    assert "stopped-abort-test" in str(exc_info.value)
    assert "no tmux session" in str(exc_info.value)

    # Clean up
    host.destroy_agent(agent)


def test_stopped_agent_with_continue_calls_on_error_callback(
    temp_host_dir: Path,
    temp_work_dir: Path,
    plugin_manager: pluggy.PluginManager,
    mngr_test_prefix: str,
) -> None:
    """Test that stopped agent with CONTINUE behavior invokes on_error callback."""

    config = MngrConfig(default_host_dir=temp_host_dir, prefix=mngr_test_prefix)
    mngr_ctx = MngrContext(config=config, pm=plugin_manager)
    provider = LocalProviderInstance(
        name=ProviderInstanceName("local"),
        host_dir=temp_host_dir,
        mngr_ctx=mngr_ctx,
    )
    host = provider.create_host(HostName("test-stopped-callback"))
    assert isinstance(host, Host)

    agent = host.create_agent_state(
        work_dir_path=temp_work_dir,
        options=CreateAgentOptions(
            name=AgentName("stopped-callback-test"),
            agent_type=AgentTypeName("generic"),
            command=CommandString("sleep 847269"),
        ),
    )

    # Don't start the agent - it should be stopped

    error_callback_calls: list[tuple[str, str]] = []

    result = send_message_to_agents(
        mngr_ctx=mngr_ctx,
        message_content="Hello",
        all_agents=True,
        error_behavior=ErrorBehavior.CONTINUE,
        on_error=lambda name, err: error_callback_calls.append((name, err)),
    )

    # Clean up
    host.destroy_agent(agent)

    # Should have recorded the failure
    assert len(result.failed_agents) == 1
    assert result.failed_agents[0][0] == "stopped-callback-test"

    # on_error callback should have been called
    assert len(error_callback_calls) == 1
    assert error_callback_calls[0][0] == "stopped-callback-test"
    assert "no tmux session" in error_callback_calls[0][1]


def test_mngr_error_during_send_message_with_abort_reraises(
    temp_host_dir: Path,
    temp_work_dir: Path,
    plugin_manager: pluggy.PluginManager,
    mngr_test_prefix: str,
) -> None:
    """Test that MngrError from send_message is re-raised with ABORT behavior."""

    config = MngrConfig(default_host_dir=temp_host_dir, prefix=mngr_test_prefix)
    mngr_ctx = MngrContext(config=config, pm=plugin_manager)
    provider = LocalProviderInstance(
        name=ProviderInstanceName("local"),
        host_dir=temp_host_dir,
        mngr_ctx=mngr_ctx,
    )
    host = provider.create_host(HostName("test-send-error-abort"))
    assert isinstance(host, Host)

    agent = host.create_agent_state(
        work_dir_path=temp_work_dir,
        options=CreateAgentOptions(
            name=AgentName("send-error-abort-test"),
            agent_type=AgentTypeName("generic"),
            command=CommandString("sleep 847270"),
        ),
    )

    # Start the agent so it's not stopped
    host.start_agents([agent.id])

    # Mock send_message to raise MngrError
    with patch.object(agent.__class__, "send_message", side_effect=MngrError("Simulated send error")):
        with pytest.raises(MngrError) as exc_info:
            send_message_to_agents(
                mngr_ctx=mngr_ctx,
                message_content="Hello",
                all_agents=True,
                error_behavior=ErrorBehavior.ABORT,
            )

        assert "Simulated send error" in str(exc_info.value)

    # Clean up
    host.destroy_agent(agent)


def test_mngr_error_during_send_message_with_continue_records_error(
    temp_host_dir: Path,
    temp_work_dir: Path,
    plugin_manager: pluggy.PluginManager,
    mngr_test_prefix: str,
) -> None:
    """Test that MngrError from send_message is recorded with CONTINUE behavior."""

    config = MngrConfig(default_host_dir=temp_host_dir, prefix=mngr_test_prefix)
    mngr_ctx = MngrContext(config=config, pm=plugin_manager)
    provider = LocalProviderInstance(
        name=ProviderInstanceName("local"),
        host_dir=temp_host_dir,
        mngr_ctx=mngr_ctx,
    )
    host = provider.create_host(HostName("test-send-error-continue"))
    assert isinstance(host, Host)

    agent = host.create_agent_state(
        work_dir_path=temp_work_dir,
        options=CreateAgentOptions(
            name=AgentName("send-error-continue-test"),
            agent_type=AgentTypeName("generic"),
            command=CommandString("sleep 847271"),
        ),
    )

    # Start the agent so it's not stopped
    host.start_agents([agent.id])

    error_callback_calls: list[tuple[str, str]] = []

    # Mock send_message to raise MngrError
    with patch.object(agent.__class__, "send_message", side_effect=MngrError("Simulated send error")):
        result = send_message_to_agents(
            mngr_ctx=mngr_ctx,
            message_content="Hello",
            all_agents=True,
            error_behavior=ErrorBehavior.CONTINUE,
            on_error=lambda name, err: error_callback_calls.append((name, err)),
        )

    # Clean up
    host.destroy_agent(agent)

    # Should have recorded the failure
    assert len(result.failed_agents) == 1
    assert result.failed_agents[0][0] == "send-error-continue-test"
    assert "Simulated send error" in result.failed_agents[0][1]

    # on_error callback should have been called
    assert len(error_callback_calls) == 1
    assert error_callback_calls[0][0] == "send-error-continue-test"
    assert "Simulated send error" in error_callback_calls[0][1]


def test_mngr_error_in_agent_loop_with_abort_reraises(
    temp_host_dir: Path,
    temp_work_dir: Path,
    plugin_manager: pluggy.PluginManager,
    mngr_test_prefix: str,
) -> None:
    """Test that MngrError in the agent iteration loop re-raises with ABORT."""

    config = MngrConfig(default_host_dir=temp_host_dir, prefix=mngr_test_prefix)
    mngr_ctx = MngrContext(config=config, pm=plugin_manager)
    provider = LocalProviderInstance(
        name=ProviderInstanceName("local"),
        host_dir=temp_host_dir,
        mngr_ctx=mngr_ctx,
    )
    host = provider.create_host(HostName("test-loop-error-abort"))
    assert isinstance(host, Host)

    agent = host.create_agent_state(
        work_dir_path=temp_work_dir,
        options=CreateAgentOptions(
            name=AgentName("loop-error-abort-test"),
            agent_type=AgentTypeName("generic"),
            command=CommandString("sleep 847272"),
        ),
    )

    # Start the agent
    host.start_agents([agent.id])

    # Mock get_lifecycle_state to raise MngrError (simulates error in agent processing)
    with patch.object(agent.__class__, "get_lifecycle_state", side_effect=MngrError("Loop processing error")):
        with pytest.raises(MngrError) as exc_info:
            send_message_to_agents(
                mngr_ctx=mngr_ctx,
                message_content="Hello",
                all_agents=True,
                error_behavior=ErrorBehavior.ABORT,
            )

        assert "Loop processing error" in str(exc_info.value)

    # Clean up
    host.destroy_agent(agent)


def test_mngr_error_in_agent_loop_with_continue_records_error(
    temp_host_dir: Path,
    temp_work_dir: Path,
    plugin_manager: pluggy.PluginManager,
    mngr_test_prefix: str,
) -> None:
    """Test that MngrError in the agent iteration loop records error with CONTINUE."""

    config = MngrConfig(default_host_dir=temp_host_dir, prefix=mngr_test_prefix)
    mngr_ctx = MngrContext(config=config, pm=plugin_manager)
    provider = LocalProviderInstance(
        name=ProviderInstanceName("local"),
        host_dir=temp_host_dir,
        mngr_ctx=mngr_ctx,
    )
    host = provider.create_host(HostName("test-loop-error-continue"))
    assert isinstance(host, Host)

    agent = host.create_agent_state(
        work_dir_path=temp_work_dir,
        options=CreateAgentOptions(
            name=AgentName("loop-error-continue-test"),
            agent_type=AgentTypeName("generic"),
            command=CommandString("sleep 847273"),
        ),
    )

    # Start the agent
    host.start_agents([agent.id])

    error_callback_calls: list[tuple[str, str]] = []

    # Mock get_lifecycle_state to raise MngrError
    with patch.object(agent.__class__, "get_lifecycle_state", side_effect=MngrError("Loop processing error")):
        result = send_message_to_agents(
            mngr_ctx=mngr_ctx,
            message_content="Hello",
            all_agents=True,
            error_behavior=ErrorBehavior.CONTINUE,
            on_error=lambda name, err: error_callback_calls.append((name, err)),
        )

    # Clean up
    host.destroy_agent(agent)

    # Should have recorded the failure
    assert len(result.failed_agents) == 1
    assert result.failed_agents[0][0] == "loop-error-continue-test"
    assert "Loop processing error" in result.failed_agents[0][1]

    # on_error callback should have been called
    assert len(error_callback_calls) == 1
    assert error_callback_calls[0][0] == "loop-error-continue-test"
