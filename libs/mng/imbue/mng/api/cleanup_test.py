"""Unit tests for cleanup API functions."""

from datetime import datetime
from datetime import timezone
from pathlib import Path

from imbue.mng.api.cleanup import execute_cleanup
from imbue.mng.api.data_types import CleanupResult
from imbue.mng.config.data_types import MngContext
from imbue.mng.interfaces.data_types import AgentInfo
from imbue.mng.interfaces.data_types import HostInfo
from imbue.mng.primitives import AgentId
from imbue.mng.primitives import AgentLifecycleState
from imbue.mng.primitives import AgentName
from imbue.mng.primitives import CleanupAction
from imbue.mng.primitives import CommandString
from imbue.mng.primitives import ErrorBehavior
from imbue.mng.primitives import HostId
from imbue.mng.primitives import ProviderInstanceName


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
    temp_mng_ctx: MngContext,
) -> None:
    """Dry-run destroy should list all agent names in destroyed_agents."""
    agents = [
        _make_test_agent_info("agent-alpha"),
        _make_test_agent_info("agent-beta"),
        _make_test_agent_info("agent-gamma"),
    ]

    result = execute_cleanup(
        mng_ctx=temp_mng_ctx,
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
    temp_mng_ctx: MngContext,
) -> None:
    """Dry-run stop should list all agent names in stopped_agents."""
    agents = [
        _make_test_agent_info("agent-one"),
        _make_test_agent_info("agent-two"),
    ]

    result = execute_cleanup(
        mng_ctx=temp_mng_ctx,
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
    temp_mng_ctx: MngContext,
) -> None:
    """Dry-run with an empty agent list should return an empty result."""
    result = execute_cleanup(
        mng_ctx=temp_mng_ctx,
        agents=[],
        action=CleanupAction.DESTROY,
        is_dry_run=True,
        error_behavior=ErrorBehavior.CONTINUE,
    )

    assert result.destroyed_agents == []
    assert result.stopped_agents == []
    assert result.errors == []


def test_execute_cleanup_dry_run_returns_cleanup_result_type(
    temp_mng_ctx: MngContext,
) -> None:
    """Dry-run should return a CleanupResult instance."""
    result = execute_cleanup(
        mng_ctx=temp_mng_ctx,
        agents=[_make_test_agent_info("test-agent")],
        action=CleanupAction.DESTROY,
        is_dry_run=True,
        error_behavior=ErrorBehavior.ABORT,
    )

    assert isinstance(result, CleanupResult)
