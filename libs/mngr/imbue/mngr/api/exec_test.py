"""Unit tests for the exec API module."""

from pathlib import Path

import pytest

from imbue.mngr.api.exec import ExecResult
from imbue.mngr.api.exec import exec_command_on_agent
from imbue.mngr.api.test_fixtures import FakeAgent
from imbue.mngr.api.test_fixtures import FakeHost
from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.primitives import AgentName


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


def test_exec_command_on_agent_uses_agent_work_dir(temp_mngr_ctx: MngrContext, tmp_path: Path) -> None:
    """Test that exec_command_on_agent defaults to the agent's work_dir."""
    agent = FakeAgent(work_dir=tmp_path, name=AgentName("test-agent"))
    host = FakeHost()

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("imbue.mngr.api.exec.load_all_agents_grouped_by_host", lambda mngr_ctx: ({}, []))
        mp.setattr(
            "imbue.mngr.api.exec.find_and_maybe_start_agent_by_name_or_id",
            lambda agent_str, agents_by_host, mngr_ctx, cmd, is_start_desired: (agent, host),
        )
        result = exec_command_on_agent(temp_mngr_ctx, "test-agent", "echo ok")

    assert result.agent_name == "test-agent"
    assert result.stdout == "ok\n"
    assert result.success is True


def test_exec_command_on_agent_uses_custom_cwd(temp_mngr_ctx: MngrContext, tmp_path: Path) -> None:
    """Test that --cwd overrides the agent's work_dir."""
    agent = FakeAgent(work_dir=tmp_path, name=AgentName("test-agent"))
    host = FakeHost()

    # Create a file in tmp_path to verify cwd is used
    (tmp_path / "marker.txt").write_text("found")

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("imbue.mngr.api.exec.load_all_agents_grouped_by_host", lambda mngr_ctx: ({}, []))
        mp.setattr(
            "imbue.mngr.api.exec.find_and_maybe_start_agent_by_name_or_id",
            lambda agent_str, agents_by_host, mngr_ctx, cmd, is_start_desired: (agent, host),
        )
        result = exec_command_on_agent(temp_mngr_ctx, "test-agent", "cat marker.txt", cwd=str(tmp_path))

    assert result.stdout == "found"
    assert result.success is True


def test_exec_command_on_agent_returns_failure_for_bad_command(temp_mngr_ctx: MngrContext, tmp_path: Path) -> None:
    """Test that a failing command returns success=False."""
    agent = FakeAgent(work_dir=tmp_path, name=AgentName("test-agent"))
    host = FakeHost()

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("imbue.mngr.api.exec.load_all_agents_grouped_by_host", lambda mngr_ctx: ({}, []))
        mp.setattr(
            "imbue.mngr.api.exec.find_and_maybe_start_agent_by_name_or_id",
            lambda agent_str, agents_by_host, mngr_ctx, cmd, is_start_desired: (agent, host),
        )
        result = exec_command_on_agent(temp_mngr_ctx, "test-agent", "false")

    assert result.success is False
