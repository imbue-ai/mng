"""Unit tests for the exec API module."""

import json
from datetime import datetime
from datetime import timezone
from pathlib import Path

from pydantic import Field

from imbue.imbue_common.frozen_model import FrozenModel
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

_AGENT_COMMAND = "sleep 98761"


class RunningTestAgent(FrozenModel):
    """A test agent with a running tmux session."""

    agent: BaseAgent = Field(description="The test agent instance")
    session_name: str = Field(description="Name of the tmux session running this agent")


def _create_running_test_agent(
    local_provider: LocalProviderInstance,
    temp_mngr_ctx: MngrContext,
    work_dir: Path,
    mngr_test_prefix: str,
) -> RunningTestAgent:
    """Create a real test agent with a running tmux session on the local provider."""
    host = local_provider.get_host(HostName("local"))

    agent_id = AgentId.generate()
    agent_name = AgentName(f"exec-test-{get_short_random_string()}")

    agent_dir = host.host_dir / "agents" / str(agent_id)
    agent_dir.mkdir(parents=True, exist_ok=True)

    data = {
        "id": str(agent_id),
        "name": str(agent_name),
        "type": "generic",
        "command": _AGENT_COMMAND,
        "work_dir": str(work_dir),
        "create_time": datetime.now(timezone.utc).isoformat(),
        "permissions": [],
        "start_on_boot": False,
    }
    (agent_dir / "data.json").write_text(json.dumps(data, indent=2))

    agent = BaseAgent(
        id=agent_id,
        host_id=host.id,
        name=agent_name,
        agent_type=AgentTypeName("generic"),
        agent_config=AgentTypeConfig(command=CommandString(_AGENT_COMMAND)),
        work_dir=work_dir,
        create_time=datetime.now(timezone.utc),
        host=host,
        mngr_ctx=temp_mngr_ctx,
    )

    session_name = f"{mngr_test_prefix}{agent_name}"
    host.execute_command(
        f"tmux new-session -d -s '{session_name}' '{_AGENT_COMMAND}'",
        timeout_seconds=5.0,
    )

    return RunningTestAgent(agent=agent, session_name=session_name)


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
    running = _create_running_test_agent(local_provider, temp_mngr_ctx, temp_work_dir, mngr_test_prefix)

    try:
        result = exec_command_on_agent(
            mngr_ctx=temp_mngr_ctx,
            agent_str=str(running.agent.name),
            command="echo hello",
        )

        assert result.agent_name == str(running.agent.name)
        assert "hello" in result.stdout
        assert result.success is True
    finally:
        cleanup_tmux_session(running.session_name)


def test_exec_command_on_agent_uses_custom_cwd(
    local_provider: LocalProviderInstance,
    temp_mngr_ctx: MngrContext,
    temp_work_dir: Path,
    tmp_path: Path,
    mngr_test_prefix: str,
) -> None:
    """Test that --cwd overrides the agent's work_dir."""
    running = _create_running_test_agent(local_provider, temp_mngr_ctx, temp_work_dir, mngr_test_prefix)

    custom_dir = tmp_path / "custom_cwd"
    custom_dir.mkdir()
    (custom_dir / "marker.txt").write_text("found")

    try:
        result = exec_command_on_agent(
            mngr_ctx=temp_mngr_ctx,
            agent_str=str(running.agent.name),
            command="cat marker.txt",
            cwd=str(custom_dir),
        )

        assert result.stdout == "found"
        assert result.success is True
    finally:
        cleanup_tmux_session(running.session_name)


def test_exec_command_on_agent_returns_failure(
    local_provider: LocalProviderInstance,
    temp_mngr_ctx: MngrContext,
    temp_work_dir: Path,
    mngr_test_prefix: str,
) -> None:
    """Test that a failing command returns success=False."""
    running = _create_running_test_agent(local_provider, temp_mngr_ctx, temp_work_dir, mngr_test_prefix)

    try:
        result = exec_command_on_agent(
            mngr_ctx=temp_mngr_ctx,
            agent_str=str(running.agent.name),
            command="false",
        )

        assert result.success is False
    finally:
        cleanup_tmux_session(running.session_name)
