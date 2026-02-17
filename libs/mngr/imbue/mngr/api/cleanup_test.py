"""Unit tests for cleanup API functions."""

from datetime import datetime
from datetime import timezone
from pathlib import Path

from imbue.mngr.api.cleanup import execute_cleanup
from imbue.mngr.api.data_types import CleanupResult
from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.interfaces.data_types import AgentInfo
from imbue.mngr.interfaces.data_types import HostInfo
from imbue.mngr.primitives import AgentId
from imbue.mngr.primitives import AgentLifecycleState
from imbue.mngr.primitives import AgentName
from imbue.mngr.primitives import CleanupAction
from imbue.mngr.primitives import CommandString
from imbue.mngr.primitives import ErrorBehavior
from imbue.mngr.primitives import HostId
from imbue.mngr.primitives import ProviderInstanceName


def _make_test_agent_info(name: str = "test-agent") -> AgentInfo:
    """Create a minimal AgentInfo for testing cleanup API functions."""
    return AgentInfo(
        id=AgentId.generate(),
        name=AgentName(name),
        type="generic",
        command=CommandString("sleep 100"),
        work_dir=Path("/tmp/test"),
        create_time=datetime.now(timezone.utc),
        start_on_boot=False,
        state=AgentLifecycleState.RUNNING,
        host=HostInfo(
            id=HostId.generate(),
            name="test-host",
            provider_name=ProviderInstanceName("local"),
        ),
    )


def test_execute_cleanup_dry_run_destroy_populates_destroyed_agents(
    temp_mngr_ctx: MngrContext,
) -> None:
    """Dry-run destroy should list all agent names in destroyed_agents."""
    agents = [
        _make_test_agent_info("agent-alpha"),
        _make_test_agent_info("agent-beta"),
        _make_test_agent_info("agent-gamma"),
    ]

    result = execute_cleanup(
        mngr_ctx=temp_mngr_ctx,
        agents=agents,
        action=CleanupAction.DESTROY,
        is_dry_run=True,
        error_behavior=ErrorBehavior.CONTINUE,
    )

    assert result.destroyed_agents == [
        AgentName("agent-alpha"),
        AgentName("agent-beta"),
        AgentName("agent-gamma"),
    ]
    assert result.stopped_agents == []
    assert result.errors == []


def test_execute_cleanup_dry_run_stop_populates_stopped_agents(
    temp_mngr_ctx: MngrContext,
) -> None:
    """Dry-run stop should list all agent names in stopped_agents."""
    agents = [
        _make_test_agent_info("agent-one"),
        _make_test_agent_info("agent-two"),
    ]

    result = execute_cleanup(
        mngr_ctx=temp_mngr_ctx,
        agents=agents,
        action=CleanupAction.STOP,
        is_dry_run=True,
        error_behavior=ErrorBehavior.CONTINUE,
    )

    assert result.stopped_agents == [
        AgentName("agent-one"),
        AgentName("agent-two"),
    ]
    assert result.destroyed_agents == []
    assert result.errors == []


def test_execute_cleanup_dry_run_with_no_agents_returns_empty_result(
    temp_mngr_ctx: MngrContext,
) -> None:
    """Dry-run with an empty agent list should return an empty result."""
    result = execute_cleanup(
        mngr_ctx=temp_mngr_ctx,
        agents=[],
        action=CleanupAction.DESTROY,
        is_dry_run=True,
        error_behavior=ErrorBehavior.CONTINUE,
    )

    assert result.destroyed_agents == []
    assert result.stopped_agents == []
    assert result.errors == []


def test_execute_cleanup_dry_run_returns_cleanup_result_type(
    temp_mngr_ctx: MngrContext,
) -> None:
    """Dry-run should return a CleanupResult instance."""
    result = execute_cleanup(
        mngr_ctx=temp_mngr_ctx,
        agents=[_make_test_agent_info("test-agent")],
        action=CleanupAction.DESTROY,
        is_dry_run=True,
        error_behavior=ErrorBehavior.ABORT,
    )

    assert isinstance(result, CleanupResult)
