"""Unit tests for the exec API module."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from imbue.mngr.api.exec import ExecResult
from imbue.mngr.api.exec import exec_command_on_agent
from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.interfaces.data_types import CommandResult


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


def test_exec_command_on_agent_uses_agent_work_dir(temp_mngr_ctx: MngrContext) -> None:
    """Test that exec_command_on_agent defaults to the agent's work_dir."""
    mock_host = MagicMock()
    mock_agent = MagicMock()
    mock_agent.name = "test-agent"
    mock_agent.work_dir = Path("/home/test/work")
    mock_host.execute_command.return_value = CommandResult(stdout="ok\n", stderr="", success=True)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "imbue.mngr.api.exec.load_all_agents_grouped_by_host",
            lambda mngr_ctx: ({}, []),
        )
        mp.setattr(
            "imbue.mngr.api.exec.find_and_maybe_start_agent_by_name_or_id",
            lambda agent_str, agents_by_host, mngr_ctx, cmd, is_start_desired: (mock_agent, mock_host),
        )

        result = exec_command_on_agent(temp_mngr_ctx, "test-agent", "echo ok")

    assert result.agent_name == "test-agent"
    assert result.stdout == "ok\n"
    assert result.success is True
    mock_host.execute_command.assert_called_once_with(
        "echo ok",
        user=None,
        cwd=Path("/home/test/work"),
        timeout_seconds=None,
    )


def test_exec_command_on_agent_uses_custom_cwd(temp_mngr_ctx: MngrContext) -> None:
    """Test that --cwd overrides the agent's work_dir."""
    mock_host = MagicMock()
    mock_agent = MagicMock()
    mock_agent.name = "test-agent"
    mock_agent.work_dir = Path("/home/test/work")
    mock_host.execute_command.return_value = CommandResult(stdout="", stderr="", success=True)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "imbue.mngr.api.exec.load_all_agents_grouped_by_host",
            lambda mngr_ctx: ({}, []),
        )
        mp.setattr(
            "imbue.mngr.api.exec.find_and_maybe_start_agent_by_name_or_id",
            lambda agent_str, agents_by_host, mngr_ctx, cmd, is_start_desired: (mock_agent, mock_host),
        )

        exec_command_on_agent(temp_mngr_ctx, "test-agent", "ls", cwd="/tmp")

    mock_host.execute_command.assert_called_once_with(
        "ls",
        user=None,
        cwd=Path("/tmp"),
        timeout_seconds=None,
    )


def test_exec_command_on_agent_passes_user_and_timeout(temp_mngr_ctx: MngrContext) -> None:
    """Test that user and timeout are passed through to execute_command."""
    mock_host = MagicMock()
    mock_agent = MagicMock()
    mock_agent.name = "test-agent"
    mock_agent.work_dir = Path("/work")
    mock_host.execute_command.return_value = CommandResult(stdout="root\n", stderr="", success=True)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "imbue.mngr.api.exec.load_all_agents_grouped_by_host",
            lambda mngr_ctx: ({}, []),
        )
        mp.setattr(
            "imbue.mngr.api.exec.find_and_maybe_start_agent_by_name_or_id",
            lambda agent_str, agents_by_host, mngr_ctx, cmd, is_start_desired: (mock_agent, mock_host),
        )

        result = exec_command_on_agent(temp_mngr_ctx, "test-agent", "whoami", user="root", timeout_seconds=30.0)

    assert result.stdout == "root\n"
    mock_host.execute_command.assert_called_once_with(
        "whoami",
        user="root",
        cwd=Path("/work"),
        timeout_seconds=30.0,
    )
