"""Unit tests for the exec API module."""

import json
from datetime import datetime
from datetime import timezone
from pathlib import Path

from imbue.mngr.agents.base_agent import BaseAgent
from imbue.mngr.api.exec import ExecResult
from imbue.mngr.api.exec import exec_command_on_agent
from imbue.mngr.config.data_types import AgentTypeConfig
from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.primitives import AgentId
from imbue.mngr.primitives import AgentName
from imbue.mngr.primitives import AgentTypeName
from imbue.mngr.primitives import CommandString
from imbue.mngr.primitives import HostName
from imbue.mngr.providers.local.instance import LocalProviderInstance
from imbue.mngr.utils.testing import cleanup_tmux_session
from imbue.mngr.utils.testing import get_short_random_string


def _create_test_agent(
    local_provider: LocalProviderInstance,
    temp_mngr_ctx: MngrContext,
    work_dir: Path,
) -> BaseAgent:
    """Create a real test agent on the local provider."""
    host = local_provider.get_host(HostName("local"))

    agent_id = AgentId.generate()
    agent_name = AgentName(f"exec-test-{get_short_random_string()}")

    agent_dir = host.host_dir / "agents" / str(agent_id)
    agent_dir.mkdir(parents=True, exist_ok=True)

    data = {
        "id": str(agent_id),
        "name": str(agent_name),
        "type": "generic",
        "command": "sleep 100000",
        "work_dir": str(work_dir),
        "create_time": datetime.now(timezone.utc).isoformat(),
        "permissions": [],
        "start_on_boot": False,
    }
    (agent_dir / "data.json").write_text(json.dumps(data, indent=2))

    agent_config = AgentTypeConfig(command=CommandString("sleep 100000"))

    return BaseAgent(
        id=agent_id,
        host_id=host.id,
        name=agent_name,
        agent_type=AgentTypeName("generic"),
        agent_config=agent_config,
        work_dir=work_dir,
        create_time=datetime.now(timezone.utc),
        host=host,
        mngr_ctx=temp_mngr_ctx,
    )


def test_exec_result_fields() -> None:
    """Test ExecResult has the expected fields."""
    result = ExecResult(
        agent_name="test-agent",
        stdout="hello\n",
        stderr="",
        success=True,
    )
    assert result.agent_name == "test-agent"
    assert result.stdout == "hello\n"
    assert result.stderr == ""
    assert result.success is True


def test_exec_result_failure() -> None:
    """Test ExecResult with a failed command."""
    result = ExecResult(
        agent_name="test-agent",
        stdout="",
        stderr="command not found\n",
        success=False,
    )
    assert result.success is False
    assert result.stderr == "command not found\n"


def test_exec_command_on_agent_runs_command(
    local_provider: LocalProviderInstance,
    temp_mngr_ctx: MngrContext,
    temp_work_dir: Path,
    mngr_test_prefix: str,
) -> None:
    """Test exec_command_on_agent runs a command on a real local agent."""
    agent = _create_test_agent(local_provider, temp_mngr_ctx, temp_work_dir)
    session_name = f"{mngr_test_prefix}{agent.name}"

    # Start tmux session so the agent is discoverable as "running"
    agent.get_host().execute_command(
        f"tmux new-session -d -s '{session_name}' 'sleep 100000'",
        timeout_seconds=5.0,
    )

    try:
        result = exec_command_on_agent(
            mngr_ctx=temp_mngr_ctx,
            agent_str=str(agent.name),
            command="echo hello",
        )

        assert result.agent_name == str(agent.name)
        assert "hello" in result.stdout
        assert result.success is True
    finally:
        cleanup_tmux_session(session_name)


def test_exec_command_on_agent_uses_custom_cwd(
    local_provider: LocalProviderInstance,
    temp_mngr_ctx: MngrContext,
    temp_work_dir: Path,
    tmp_path: Path,
    mngr_test_prefix: str,
) -> None:
    """Test that --cwd overrides the agent's work_dir."""
    agent = _create_test_agent(local_provider, temp_mngr_ctx, temp_work_dir)
    session_name = f"{mngr_test_prefix}{agent.name}"

    # Create a marker file in a different directory
    custom_dir = tmp_path / "custom_cwd"
    custom_dir.mkdir()
    (custom_dir / "marker.txt").write_text("found")

    agent.get_host().execute_command(
        f"tmux new-session -d -s '{session_name}' 'sleep 100000'",
        timeout_seconds=5.0,
    )

    try:
        result = exec_command_on_agent(
            mngr_ctx=temp_mngr_ctx,
            agent_str=str(agent.name),
            command="cat marker.txt",
            cwd=str(custom_dir),
        )

        assert result.stdout == "found"
        assert result.success is True
    finally:
        cleanup_tmux_session(session_name)


def test_exec_command_on_agent_returns_failure(
    local_provider: LocalProviderInstance,
    temp_mngr_ctx: MngrContext,
    temp_work_dir: Path,
    mngr_test_prefix: str,
) -> None:
    """Test that a failing command returns success=False."""
    agent = _create_test_agent(local_provider, temp_mngr_ctx, temp_work_dir)
    session_name = f"{mngr_test_prefix}{agent.name}"

    agent.get_host().execute_command(
        f"tmux new-session -d -s '{session_name}' 'sleep 100000'",
        timeout_seconds=5.0,
    )

    try:
        result = exec_command_on_agent(
            mngr_ctx=temp_mngr_ctx,
            agent_str=str(agent.name),
            command="false",
        )

        assert result.success is False
    finally:
        cleanup_tmux_session(session_name)
