"""Integration tests for the list API module."""

import time
from datetime import datetime
from datetime import timezone
from pathlib import Path
from unittest.mock import MagicMock

import pluggy
from click.testing import CliRunner

from imbue.mngr.api.list import AgentErrorInfo
from imbue.mngr.api.list import AgentInfo
from imbue.mngr.api.list import ErrorInfo
from imbue.mngr.api.list import HostErrorInfo
from imbue.mngr.api.list import ListResult
from imbue.mngr.api.list import ProviderErrorInfo
from imbue.mngr.api.list import _agent_to_cel_context
from imbue.mngr.api.list import _apply_cel_filters
from imbue.mngr.api.list import _get_persisted_agent_data
from imbue.mngr.api.list import list_agents
from imbue.mngr.cli.create import create
from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.errors import MngrError
from imbue.mngr.interfaces.data_types import CpuResources
from imbue.mngr.interfaces.data_types import HostInfo
from imbue.mngr.interfaces.data_types import HostResources
from imbue.mngr.interfaces.data_types import SSHInfo
from imbue.mngr.primitives import AgentId
from imbue.mngr.primitives import AgentLifecycleState
from imbue.mngr.primitives import AgentName
from imbue.mngr.primitives import CommandString
from imbue.mngr.primitives import ErrorBehavior
from imbue.mngr.primitives import HostId
from imbue.mngr.primitives import ProviderInstanceName
from imbue.mngr.utils.cel_utils import compile_cel_filters
from imbue.mngr.utils.testing import tmux_session_cleanup

# =============================================================================
# Tests for _get_persisted_agent_data helper function
# =============================================================================


def test_get_persisted_agent_data_returns_matching_agent() -> None:
    """_get_persisted_agent_data should return the agent data when found."""
    host_id = HostId.generate()
    agent_id = AgentId.generate()

    mock_provider = MagicMock()
    mock_provider.list_persisted_agent_data_for_host.return_value = [
        {"id": str(agent_id), "name": "test-agent", "type": "claude"},
        {"id": str(AgentId.generate()), "name": "other-agent", "type": "codex"},
    ]

    result = _get_persisted_agent_data(mock_provider, host_id, agent_id)

    assert result is not None
    assert result["id"] == str(agent_id)
    assert result["name"] == "test-agent"
    mock_provider.list_persisted_agent_data_for_host.assert_called_once_with(host_id)


def test_get_persisted_agent_data_returns_none_when_not_found() -> None:
    """_get_persisted_agent_data should return None when agent not found."""
    host_id = HostId.generate()
    agent_id = AgentId.generate()

    mock_provider = MagicMock()
    mock_provider.list_persisted_agent_data_for_host.return_value = [
        {"id": str(AgentId.generate()), "name": "other-agent"},
    ]

    result = _get_persisted_agent_data(mock_provider, host_id, agent_id)

    assert result is None


def test_get_persisted_agent_data_returns_none_when_provider_returns_empty() -> None:
    """_get_persisted_agent_data should return None when provider returns empty list."""
    host_id = HostId.generate()
    agent_id = AgentId.generate()

    mock_provider = MagicMock()
    mock_provider.list_persisted_agent_data_for_host.return_value = []

    result = _get_persisted_agent_data(mock_provider, host_id, agent_id)

    assert result is None


def test_get_persisted_agent_data_handles_exception() -> None:
    """_get_persisted_agent_data should handle exceptions gracefully."""
    host_id = HostId.generate()
    agent_id = AgentId.generate()

    mock_provider = MagicMock()
    mock_provider.list_persisted_agent_data_for_host.side_effect = OSError("Network error")

    result = _get_persisted_agent_data(mock_provider, host_id, agent_id)

    assert result is None


# =============================================================================
# Error Info Tests
# =============================================================================


def test_error_info_build_creates_error_info() -> None:
    """Test that ErrorInfo.build creates an error info from an exception."""
    exception = RuntimeError("Test error message")

    error_info = ErrorInfo.build(exception)

    assert error_info.exception_type == "RuntimeError"
    assert error_info.message == "Test error message"


def test_error_info_build_handles_mngr_error() -> None:
    """Test that ErrorInfo.build handles MngrError subclasses."""

    class CustomMngrError(MngrError):
        """Custom test error."""

    exception = CustomMngrError("Custom error")

    error_info = ErrorInfo.build(exception)

    assert error_info.exception_type == "CustomMngrError"
    assert error_info.message == "Custom error"


def test_provider_error_info_build_for_provider() -> None:
    """Test that ProviderErrorInfo.build_for_provider creates error with provider context."""
    exception = RuntimeError("Provider failed")
    provider_name = ProviderInstanceName("test-provider")

    error_info = ProviderErrorInfo.build_for_provider(exception, provider_name)

    assert error_info.exception_type == "RuntimeError"
    assert error_info.message == "Provider failed"
    assert error_info.provider_name == provider_name


def test_host_error_info_build_for_host() -> None:
    """Test that HostErrorInfo.build_for_host creates error with host context."""
    exception = RuntimeError("Host failed")
    host_id = HostId.generate()

    error_info = HostErrorInfo.build_for_host(exception, host_id)

    assert error_info.exception_type == "RuntimeError"
    assert error_info.message == "Host failed"
    assert error_info.host_id == host_id


def test_agent_error_info_build_for_agent() -> None:
    """Test that AgentErrorInfo.build_for_agent creates error with agent context."""
    exception = RuntimeError("Agent failed")
    agent_id = AgentId.generate()

    error_info = AgentErrorInfo.build_for_agent(exception, agent_id)

    assert error_info.exception_type == "RuntimeError"
    assert error_info.message == "Agent failed"
    assert error_info.agent_id == agent_id


def test_list_result_defaults_to_empty_lists() -> None:
    """Test that ListResult defaults to empty lists."""
    result = ListResult()

    assert result.agents == []
    assert result.errors == []


def test_agent_to_cel_context_basic_fields() -> None:
    """Test that _agent_to_cel_context converts basic AgentInfo fields."""
    host_info = HostInfo(
        id=HostId.generate(),
        name="test-host",
        provider_name=ProviderInstanceName("local"),
    )
    agent_info = AgentInfo(
        id=AgentId.generate(),
        name=AgentName("test-agent"),
        type="claude",
        command=CommandString("sleep 100"),
        work_dir=Path("/work/dir"),
        create_time=datetime.now(timezone.utc),
        start_on_boot=False,
        lifecycle_state=AgentLifecycleState.RUNNING,
        host=host_info,
    )

    context = _agent_to_cel_context(agent_info)

    assert context["type"] == "agent"
    assert context["name"] == "test-agent"
    assert context["host"]["name"] == "test-host"
    assert context["host"]["provider"] == "local"
    assert "age" in context


def test_agent_to_cel_context_with_runtime() -> None:
    """Test that _agent_to_cel_context includes runtime when available."""
    host_info = HostInfo(
        id=HostId.generate(),
        name="test-host",
        provider_name=ProviderInstanceName("local"),
    )
    agent_info = AgentInfo(
        id=AgentId.generate(),
        name=AgentName("test-agent"),
        type="claude",
        command=CommandString("sleep 100"),
        work_dir=Path("/work/dir"),
        create_time=datetime.now(timezone.utc),
        start_on_boot=False,
        lifecycle_state=AgentLifecycleState.RUNNING,
        runtime_seconds=123.45,
        host=host_info,
    )

    context = _agent_to_cel_context(agent_info)

    assert context["runtime"] == 123.45


def test_agent_to_cel_context_with_activity_time() -> None:
    """Test that _agent_to_cel_context computes idle from activity times."""
    host_info = HostInfo(
        id=HostId.generate(),
        name="test-host",
        provider_name=ProviderInstanceName("local"),
    )
    activity_time = datetime.now(timezone.utc)
    agent_info = AgentInfo(
        id=AgentId.generate(),
        name=AgentName("test-agent"),
        type="claude",
        command=CommandString("sleep 100"),
        work_dir=Path("/work/dir"),
        create_time=datetime.now(timezone.utc),
        start_on_boot=False,
        lifecycle_state=AgentLifecycleState.RUNNING,
        user_activity_time=activity_time,
        host=host_info,
    )

    context = _agent_to_cel_context(agent_info)

    # Idle should be computed and be very small (just computed)
    assert "idle" in context
    assert context["idle"] >= 0


def test_agent_to_cel_context_with_lifecycle_state() -> None:
    """Test that _agent_to_cel_context flattens lifecycle state."""
    host_info = HostInfo(
        id=HostId.generate(),
        name="test-host",
        provider_name=ProviderInstanceName("local"),
    )
    agent_info = AgentInfo(
        id=AgentId.generate(),
        name=AgentName("test-agent"),
        type="claude",
        command=CommandString("sleep 100"),
        work_dir=Path("/work/dir"),
        create_time=datetime.now(timezone.utc),
        start_on_boot=False,
        lifecycle_state=AgentLifecycleState.STOPPED,
        host=host_info,
    )

    context = _agent_to_cel_context(agent_info)

    assert context["state"] == "stopped"


def test_apply_cel_filters_with_include_filter() -> None:
    """Test that _apply_cel_filters includes matching agents."""
    host_info = HostInfo(
        id=HostId.generate(),
        name="test-host",
        provider_name=ProviderInstanceName("local"),
    )
    agent_info = AgentInfo(
        id=AgentId.generate(),
        name=AgentName("my-agent"),
        type="claude",
        command=CommandString("sleep 100"),
        work_dir=Path("/work/dir"),
        create_time=datetime.now(timezone.utc),
        start_on_boot=False,
        lifecycle_state=AgentLifecycleState.RUNNING,
        host=host_info,
    )

    include_filters, exclude_filters = compile_cel_filters(
        include_filters=('name == "my-agent"',),
        exclude_filters=(),
    )

    result = _apply_cel_filters(agent_info, include_filters, exclude_filters)

    assert result is True


def test_apply_cel_filters_with_non_matching_include() -> None:
    """Test that _apply_cel_filters excludes non-matching agents."""
    host_info = HostInfo(
        id=HostId.generate(),
        name="test-host",
        provider_name=ProviderInstanceName("local"),
    )
    agent_info = AgentInfo(
        id=AgentId.generate(),
        name=AgentName("other-agent"),
        type="claude",
        command=CommandString("sleep 100"),
        work_dir=Path("/work/dir"),
        create_time=datetime.now(timezone.utc),
        start_on_boot=False,
        lifecycle_state=AgentLifecycleState.RUNNING,
        host=host_info,
    )

    include_filters, exclude_filters = compile_cel_filters(
        include_filters=('name == "my-agent"',),
        exclude_filters=(),
    )

    result = _apply_cel_filters(agent_info, include_filters, exclude_filters)

    assert result is False


def test_apply_cel_filters_with_exclude_filter() -> None:
    """Test that _apply_cel_filters excludes matching agents."""
    host_info = HostInfo(
        id=HostId.generate(),
        name="test-host",
        provider_name=ProviderInstanceName("local"),
    )
    agent_info = AgentInfo(
        id=AgentId.generate(),
        name=AgentName("excluded-agent"),
        type="claude",
        command=CommandString("sleep 100"),
        work_dir=Path("/work/dir"),
        create_time=datetime.now(timezone.utc),
        start_on_boot=False,
        lifecycle_state=AgentLifecycleState.RUNNING,
        host=host_info,
    )

    include_filters, exclude_filters = compile_cel_filters(
        include_filters=(),
        exclude_filters=('name == "excluded-agent"',),
    )

    result = _apply_cel_filters(agent_info, include_filters, exclude_filters)

    assert result is False


def test_apply_cel_filters_with_state_filter() -> None:
    """Test filtering by lifecycle state."""
    host_info = HostInfo(
        id=HostId.generate(),
        name="test-host",
        provider_name=ProviderInstanceName("local"),
    )
    agent_info = AgentInfo(
        id=AgentId.generate(),
        name=AgentName("test-agent"),
        type="claude",
        command=CommandString("sleep 100"),
        work_dir=Path("/work/dir"),
        create_time=datetime.now(timezone.utc),
        start_on_boot=False,
        lifecycle_state=AgentLifecycleState.RUNNING,
        host=host_info,
    )

    include_filters, exclude_filters = compile_cel_filters(
        include_filters=('state == "running"',),
        exclude_filters=(),
    )

    result = _apply_cel_filters(agent_info, include_filters, exclude_filters)

    assert result is True


def test_apply_cel_filters_with_host_provider_filter() -> None:
    """Test filtering by host provider using dot notation."""
    host_info = HostInfo(
        id=HostId.generate(),
        name="test-host",
        provider_name=ProviderInstanceName("local"),
    )
    agent_info = AgentInfo(
        id=AgentId.generate(),
        name=AgentName("test-agent"),
        type="claude",
        command=CommandString("sleep 100"),
        work_dir=Path("/work/dir"),
        create_time=datetime.now(timezone.utc),
        start_on_boot=False,
        lifecycle_state=AgentLifecycleState.RUNNING,
        host=host_info,
    )

    include_filters, exclude_filters = compile_cel_filters(
        include_filters=('host.provider == "local"',),
        exclude_filters=(),
    )

    result = _apply_cel_filters(agent_info, include_filters, exclude_filters)

    assert result is True


def test_list_agents_returns_empty_when_no_agents(
    temp_mngr_ctx: MngrContext,
) -> None:
    """Test that list_agents returns empty result when no agents exist."""
    result = list_agents(
        mngr_ctx=temp_mngr_ctx,
    )

    assert result.agents == []
    assert result.errors == []


def test_list_agents_with_agent(
    cli_runner: CliRunner,
    temp_work_dir: Path,
    temp_mngr_ctx: MngrContext,
    mngr_test_prefix: str,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that list_agents returns agents that exist."""
    agent_name = f"test-list-{int(time.time())}"
    session_name = f"{mngr_test_prefix}{agent_name}"

    with tmux_session_cleanup(session_name):
        # Create an agent first
        create_result = cli_runner.invoke(
            create,
            [
                "--name",
                agent_name,
                "--agent-cmd",
                "sleep 847291",
                "--source",
                str(temp_work_dir),
                "--no-connect",
                "--await-ready",
                "--no-copy-work-dir",
                "--no-ensure-clean",
            ],
            obj=plugin_manager,
            catch_exceptions=False,
        )
        assert create_result.exit_code == 0, f"Create failed: {create_result.output}"

        # Now list agents
        result = list_agents(mngr_ctx=temp_mngr_ctx)

        assert len(result.agents) >= 1
        agent_names = [a.name for a in result.agents]
        assert AgentName(agent_name) in agent_names


def test_list_agents_with_include_filter(
    cli_runner: CliRunner,
    temp_work_dir: Path,
    temp_mngr_ctx: MngrContext,
    mngr_test_prefix: str,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that list_agents applies include filters correctly."""
    agent_name = f"test-filter-{int(time.time())}"
    session_name = f"{mngr_test_prefix}{agent_name}"

    with tmux_session_cleanup(session_name):
        # Create an agent
        create_result = cli_runner.invoke(
            create,
            [
                "--name",
                agent_name,
                "--agent-cmd",
                "sleep 938274",
                "--source",
                str(temp_work_dir),
                "--no-connect",
                "--await-ready",
                "--no-copy-work-dir",
                "--no-ensure-clean",
            ],
            obj=plugin_manager,
            catch_exceptions=False,
        )
        assert create_result.exit_code == 0

        # List with filter that matches
        result = list_agents(
            mngr_ctx=temp_mngr_ctx,
            include_filters=(f'name == "{agent_name}"',),
        )

        assert len(result.agents) == 1
        assert result.agents[0].name == AgentName(agent_name)


def test_list_agents_with_exclude_filter(
    cli_runner: CliRunner,
    temp_work_dir: Path,
    temp_mngr_ctx: MngrContext,
    mngr_test_prefix: str,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that list_agents applies exclude filters correctly."""
    agent_name = f"test-exclude-{int(time.time())}"
    session_name = f"{mngr_test_prefix}{agent_name}"

    with tmux_session_cleanup(session_name):
        # Create an agent
        create_result = cli_runner.invoke(
            create,
            [
                "--name",
                agent_name,
                "--agent-cmd",
                "sleep 726485",
                "--source",
                str(temp_work_dir),
                "--no-connect",
                "--await-ready",
                "--no-copy-work-dir",
                "--no-ensure-clean",
            ],
            obj=plugin_manager,
            catch_exceptions=False,
        )
        assert create_result.exit_code == 0

        # List with filter that excludes the agent
        result = list_agents(
            mngr_ctx=temp_mngr_ctx,
            exclude_filters=(f'name == "{agent_name}"',),
        )

        agent_names = [a.name for a in result.agents]
        assert AgentName(agent_name) not in agent_names


def test_list_agents_with_callbacks(
    cli_runner: CliRunner,
    temp_work_dir: Path,
    temp_mngr_ctx: MngrContext,
    mngr_test_prefix: str,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that list_agents calls on_agent callback for each agent."""
    agent_name = f"test-callback-{int(time.time())}"
    session_name = f"{mngr_test_prefix}{agent_name}"

    agents_received: list[AgentInfo] = []

    def on_agent(agent: AgentInfo) -> None:
        agents_received.append(agent)

    with tmux_session_cleanup(session_name):
        # Create an agent
        create_result = cli_runner.invoke(
            create,
            [
                "--name",
                agent_name,
                "--agent-cmd",
                "sleep 619274",
                "--source",
                str(temp_work_dir),
                "--no-connect",
                "--await-ready",
                "--no-copy-work-dir",
                "--no-ensure-clean",
            ],
            obj=plugin_manager,
            catch_exceptions=False,
        )
        assert create_result.exit_code == 0

        # List with callback
        result = list_agents(
            mngr_ctx=temp_mngr_ctx,
            on_agent=on_agent,
        )

        # Callback should have been called for each agent
        assert len(agents_received) == len(result.agents)
        if result.agents:
            assert agents_received[0].name == result.agents[0].name


def test_list_agents_with_error_behavior_continue(
    temp_mngr_ctx: MngrContext,
) -> None:
    """Test that list_agents with CONTINUE error behavior doesn't raise."""
    # This should not raise even if there are issues
    result = list_agents(
        mngr_ctx=temp_mngr_ctx,
        error_behavior=ErrorBehavior.CONTINUE,
    )

    # Should return a result, possibly empty
    assert isinstance(result, ListResult)


# =============================================================================
# Extended HostInfo Field Tests
# =============================================================================


def test_agent_to_cel_context_with_host_state() -> None:
    """Test that _agent_to_cel_context includes host.state field."""
    host_info = HostInfo(
        id=HostId.generate(),
        name="test-host",
        provider_name=ProviderInstanceName("local"),
        state="running",
    )
    agent_info = AgentInfo(
        id=AgentId.generate(),
        name=AgentName("test-agent"),
        type="claude",
        command=CommandString("sleep 100"),
        work_dir=Path("/work/dir"),
        create_time=datetime.now(timezone.utc),
        start_on_boot=False,
        lifecycle_state=AgentLifecycleState.RUNNING,
        host=host_info,
    )

    context = _agent_to_cel_context(agent_info)

    assert context["host"]["state"] == "running"


def test_agent_to_cel_context_with_host_resources() -> None:
    """Test that _agent_to_cel_context includes host.resource fields."""
    resources = HostResources(cpu=CpuResources(count=4), memory_gb=16.0, disk_gb=100.0)
    host_info = HostInfo(
        id=HostId.generate(),
        name="test-host",
        provider_name=ProviderInstanceName("modal"),
        resource=resources,
    )
    agent_info = AgentInfo(
        id=AgentId.generate(),
        name=AgentName("test-agent"),
        type="claude",
        command=CommandString("sleep 100"),
        work_dir=Path("/work/dir"),
        create_time=datetime.now(timezone.utc),
        start_on_boot=False,
        lifecycle_state=AgentLifecycleState.RUNNING,
        host=host_info,
    )

    context = _agent_to_cel_context(agent_info)

    assert context["host"]["resource"]["memory_gb"] == 16.0
    assert context["host"]["resource"]["disk_gb"] == 100.0


def test_agent_to_cel_context_with_host_ssh() -> None:
    """Test that _agent_to_cel_context includes host.ssh fields."""
    ssh_info = SSHInfo(
        user="root",
        host="example.com",
        port=22,
        key_path=Path("/keys/id_rsa"),
        command="ssh -i /keys/id_rsa -p 22 root@example.com",
    )
    host_info = HostInfo(
        id=HostId.generate(),
        name="test-host",
        provider_name=ProviderInstanceName("docker"),
        ssh=ssh_info,
    )
    agent_info = AgentInfo(
        id=AgentId.generate(),
        name=AgentName("test-agent"),
        type="claude",
        command=CommandString("sleep 100"),
        work_dir=Path("/work/dir"),
        create_time=datetime.now(timezone.utc),
        start_on_boot=False,
        lifecycle_state=AgentLifecycleState.RUNNING,
        host=host_info,
    )

    context = _agent_to_cel_context(agent_info)

    assert context["host"]["ssh"]["user"] == "root"
    assert context["host"]["ssh"]["host"] == "example.com"
    assert context["host"]["ssh"]["port"] == 22


def test_apply_cel_filters_with_host_state_filter() -> None:
    """Test filtering by host.state."""
    host_info = HostInfo(
        id=HostId.generate(),
        name="test-host",
        provider_name=ProviderInstanceName("local"),
        state="running",
    )
    agent_info = AgentInfo(
        id=AgentId.generate(),
        name=AgentName("test-agent"),
        type="claude",
        command=CommandString("sleep 100"),
        work_dir=Path("/work/dir"),
        create_time=datetime.now(timezone.utc),
        start_on_boot=False,
        lifecycle_state=AgentLifecycleState.RUNNING,
        host=host_info,
    )

    include_filters, exclude_filters = compile_cel_filters(
        include_filters=('host.state == "running"',),
        exclude_filters=(),
    )

    result = _apply_cel_filters(agent_info, include_filters, exclude_filters)

    assert result is True


def test_apply_cel_filters_with_host_resource_filter() -> None:
    """Test filtering by host.resource.memory_gb."""
    resources = HostResources(cpu=CpuResources(count=8), memory_gb=32.0, disk_gb=500.0)
    host_info = HostInfo(
        id=HostId.generate(),
        name="test-host",
        provider_name=ProviderInstanceName("modal"),
        resource=resources,
    )
    agent_info = AgentInfo(
        id=AgentId.generate(),
        name=AgentName("test-agent"),
        type="claude",
        command=CommandString("sleep 100"),
        work_dir=Path("/work/dir"),
        create_time=datetime.now(timezone.utc),
        start_on_boot=False,
        lifecycle_state=AgentLifecycleState.RUNNING,
        host=host_info,
    )

    include_filters, exclude_filters = compile_cel_filters(
        include_filters=("host.resource.memory_gb >= 16",),
        exclude_filters=(),
    )

    result = _apply_cel_filters(agent_info, include_filters, exclude_filters)

    assert result is True


def test_apply_cel_filters_with_host_uptime_filter() -> None:
    """Test filtering by host.uptime_seconds."""
    host_info = HostInfo(
        id=HostId.generate(),
        name="test-host",
        provider_name=ProviderInstanceName("local"),
        # More than a day (86400 seconds)
        uptime_seconds=100000.0,
    )
    agent_info = AgentInfo(
        id=AgentId.generate(),
        name=AgentName("test-agent"),
        type="claude",
        command=CommandString("sleep 100"),
        work_dir=Path("/work/dir"),
        create_time=datetime.now(timezone.utc),
        start_on_boot=False,
        lifecycle_state=AgentLifecycleState.RUNNING,
        host=host_info,
    )

    # Filter for hosts running more than a day (86400 seconds)
    include_filters, exclude_filters = compile_cel_filters(
        include_filters=("host.uptime_seconds > 86400",),
        exclude_filters=(),
    )

    result = _apply_cel_filters(agent_info, include_filters, exclude_filters)

    assert result is True


def test_apply_cel_filters_with_host_tags_filter() -> None:
    """Test filtering by host.tags."""
    host_info = HostInfo(
        id=HostId.generate(),
        name="test-host",
        provider_name=ProviderInstanceName("modal"),
        tags={"env": "production", "team": "ml"},
    )
    agent_info = AgentInfo(
        id=AgentId.generate(),
        name=AgentName("test-agent"),
        type="claude",
        command=CommandString("sleep 100"),
        work_dir=Path("/work/dir"),
        create_time=datetime.now(timezone.utc),
        start_on_boot=False,
        lifecycle_state=AgentLifecycleState.RUNNING,
        host=host_info,
    )

    include_filters, exclude_filters = compile_cel_filters(
        include_filters=('host.tags.env == "production"',),
        exclude_filters=(),
    )

    result = _apply_cel_filters(agent_info, include_filters, exclude_filters)

    assert result is True


# =============================================================================
# Idle Mode and Idle Seconds Tests
# =============================================================================


def test_agent_to_cel_context_with_idle_mode() -> None:
    """Test that _agent_to_cel_context includes idle_mode field."""
    host_info = HostInfo(
        id=HostId.generate(),
        name="test-host",
        provider_name=ProviderInstanceName("local"),
    )
    agent_info = AgentInfo(
        id=AgentId.generate(),
        name=AgentName("test-agent"),
        type="claude",
        command=CommandString("sleep 100"),
        work_dir=Path("/work/dir"),
        create_time=datetime.now(timezone.utc),
        start_on_boot=False,
        lifecycle_state=AgentLifecycleState.RUNNING,
        idle_mode="agent",
        host=host_info,
    )

    context = _agent_to_cel_context(agent_info)

    assert context["idle_mode"] == "agent"


def test_agent_to_cel_context_with_idle_seconds() -> None:
    """Test that _agent_to_cel_context includes idle_seconds field."""
    host_info = HostInfo(
        id=HostId.generate(),
        name="test-host",
        provider_name=ProviderInstanceName("local"),
    )
    agent_info = AgentInfo(
        id=AgentId.generate(),
        name=AgentName("test-agent"),
        type="claude",
        command=CommandString("sleep 100"),
        work_dir=Path("/work/dir"),
        create_time=datetime.now(timezone.utc),
        start_on_boot=False,
        lifecycle_state=AgentLifecycleState.RUNNING,
        idle_seconds=300.5,
        host=host_info,
    )

    context = _agent_to_cel_context(agent_info)

    assert context["idle_seconds"] == 300.5


def test_apply_cel_filters_with_idle_mode_filter() -> None:
    """Test filtering by idle_mode."""
    host_info = HostInfo(
        id=HostId.generate(),
        name="test-host",
        provider_name=ProviderInstanceName("local"),
    )
    agent_info = AgentInfo(
        id=AgentId.generate(),
        name=AgentName("test-agent"),
        type="claude",
        command=CommandString("sleep 100"),
        work_dir=Path("/work/dir"),
        create_time=datetime.now(timezone.utc),
        start_on_boot=False,
        lifecycle_state=AgentLifecycleState.RUNNING,
        idle_mode="user",
        host=host_info,
    )

    include_filters, exclude_filters = compile_cel_filters(
        include_filters=('idle_mode == "user"',),
        exclude_filters=(),
    )

    result = _apply_cel_filters(agent_info, include_filters, exclude_filters)

    assert result is True


def test_apply_cel_filters_with_idle_seconds_filter() -> None:
    """Test filtering by idle_seconds."""
    host_info = HostInfo(
        id=HostId.generate(),
        name="test-host",
        provider_name=ProviderInstanceName("local"),
    )
    agent_info = AgentInfo(
        id=AgentId.generate(),
        name=AgentName("test-agent"),
        type="claude",
        command=CommandString("sleep 100"),
        work_dir=Path("/work/dir"),
        create_time=datetime.now(timezone.utc),
        start_on_boot=False,
        lifecycle_state=AgentLifecycleState.RUNNING,
        idle_seconds=600.0,
        host=host_info,
    )

    # Filter for agents idle more than 5 minutes (300 seconds)
    include_filters, exclude_filters = compile_cel_filters(
        include_filters=("idle_seconds > 300",),
        exclude_filters=(),
    )

    result = _apply_cel_filters(agent_info, include_filters, exclude_filters)

    assert result is True


def test_list_agents_populates_idle_mode(
    cli_runner: CliRunner,
    temp_work_dir: Path,
    temp_mngr_ctx: MngrContext,
    mngr_test_prefix: str,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that list_agents populates idle_mode from the host's activity config."""
    agent_name = f"test-idle-mode-{int(time.time())}"
    session_name = f"{mngr_test_prefix}{agent_name}"

    with tmux_session_cleanup(session_name):
        # Create an agent
        create_result = cli_runner.invoke(
            create,
            [
                "--name",
                agent_name,
                "--agent-cmd",
                "sleep 123456",
                "--source",
                str(temp_work_dir),
                "--no-connect",
                "--await-ready",
                "--no-copy-work-dir",
                "--no-ensure-clean",
            ],
            obj=plugin_manager,
            catch_exceptions=False,
        )
        assert create_result.exit_code == 0, f"Create failed: {create_result.output}"

        # List agents and check idle_mode is populated
        result = list_agents(mngr_ctx=temp_mngr_ctx)

        # Find our agent
        our_agent = next((a for a in result.agents if a.name == AgentName(agent_name)), None)
        assert our_agent is not None, f"Agent {agent_name} not found in list"

        # idle_mode should be populated (default is "agent")
        assert our_agent.idle_mode is not None
        assert our_agent.idle_mode == "io"


def test_list_agents_with_provider_names_filter(
    cli_runner: CliRunner,
    temp_work_dir: Path,
    temp_mngr_ctx: MngrContext,
    mngr_test_prefix: str,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that list_agents filters by provider_names."""
    agent_name = f"test-provider-filter-{int(time.time())}"
    session_name = f"{mngr_test_prefix}{agent_name}"

    with tmux_session_cleanup(session_name):
        # Create an agent on the local provider
        create_result = cli_runner.invoke(
            create,
            [
                "--name",
                agent_name,
                "--agent-cmd",
                "sleep 234567",
                "--source",
                str(temp_work_dir),
                "--no-connect",
                "--await-ready",
                "--no-copy-work-dir",
                "--no-ensure-clean",
            ],
            obj=plugin_manager,
            catch_exceptions=False,
        )
        assert create_result.exit_code == 0, f"Create failed: {create_result.output}"

        # List agents filtering to local provider - should find the agent
        result = list_agents(mngr_ctx=temp_mngr_ctx, provider_names=("local",))

        agent_names = [a.name for a in result.agents]
        assert AgentName(agent_name) in agent_names

        # List agents filtering to nonexistent provider - should not find any agents
        result_empty = list_agents(mngr_ctx=temp_mngr_ctx, provider_names=("nonexistent",))

        assert len(result_empty.agents) == 0
