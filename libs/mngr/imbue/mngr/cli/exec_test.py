"""Unit tests for the exec CLI command."""

import json

import pluggy
import pytest
from click.testing import CliRunner

from imbue.mngr.api.exec import ExecResult
from imbue.mngr.cli.exec import ExecCliOptions
from imbue.mngr.cli.exec import exec_command


def test_exec_cli_options_fields() -> None:
    """Test ExecCliOptions has required fields."""
    opts = ExecCliOptions(
        agent="my-agent",
        command_arg="echo hello",
        user=None,
        cwd=None,
        timeout=None,
        start=True,
        output_format="human",
        quiet=False,
        verbose=0,
        log_file=None,
        log_commands=None,
        log_command_output=None,
        log_env_vars=None,
        project_context_path=None,
        plugin=(),
        disable_plugin=(),
    )
    assert opts.agent == "my-agent"
    assert opts.command_arg == "echo hello"
    assert opts.user is None
    assert opts.cwd is None
    assert opts.timeout is None
    assert opts.start is True


def test_exec_requires_agent_and_command(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that exec requires both AGENT and COMMAND arguments."""
    result = cli_runner.invoke(
        exec_command,
        [],
        obj=plugin_manager,
        catch_exceptions=True,
    )
    assert result.exit_code != 0


def test_exec_requires_command(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that exec requires the COMMAND argument."""
    result = cli_runner.invoke(
        exec_command,
        ["my-agent"],
        obj=plugin_manager,
        catch_exceptions=True,
    )
    assert result.exit_code != 0


def test_exec_nonexistent_agent(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test executing on a non-existent agent."""
    result = cli_runner.invoke(
        exec_command,
        ["nonexistent-agent-99999", "echo hello"],
        obj=plugin_manager,
        catch_exceptions=True,
    )
    assert result.exit_code != 0


def test_exec_human_output_success(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test human output format for a successful command."""
    mock_result = ExecResult(
        agent_name="test-agent",
        stdout="hello world\n",
        stderr="",
        success=True,
    )
    monkeypatch.setattr(
        "imbue.mngr.cli.exec.exec_command_on_agent",
        lambda **kwargs: mock_result,
    )

    result = cli_runner.invoke(
        exec_command,
        ["test-agent", "echo hello world"],
        obj=plugin_manager,
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert "hello world" in result.output
    assert "Command succeeded" in result.output


def test_exec_human_output_failure(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test human output format for a failed command."""
    mock_result = ExecResult(
        agent_name="test-agent",
        stdout="",
        stderr="command not found\n",
        success=False,
    )
    monkeypatch.setattr(
        "imbue.mngr.cli.exec.exec_command_on_agent",
        lambda **kwargs: mock_result,
    )

    result = cli_runner.invoke(
        exec_command,
        ["test-agent", "bad-command"],
        obj=plugin_manager,
        catch_exceptions=False,
    )

    assert result.exit_code == 1


def test_exec_json_output(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test JSON output format."""
    mock_result = ExecResult(
        agent_name="test-agent",
        stdout="hello\n",
        stderr="",
        success=True,
    )
    monkeypatch.setattr(
        "imbue.mngr.cli.exec.exec_command_on_agent",
        lambda **kwargs: mock_result,
    )

    result = cli_runner.invoke(
        exec_command,
        ["test-agent", "echo hello", "--format", "json"],
        obj=plugin_manager,
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    output = json.loads(result.output.strip())
    assert output["agent"] == "test-agent"
    assert output["stdout"] == "hello\n"
    assert output["stderr"] == ""
    assert output["success"] is True


def test_exec_jsonl_output(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test JSONL output format."""
    mock_result = ExecResult(
        agent_name="test-agent",
        stdout="hello\n",
        stderr="",
        success=True,
    )
    monkeypatch.setattr(
        "imbue.mngr.cli.exec.exec_command_on_agent",
        lambda **kwargs: mock_result,
    )

    result = cli_runner.invoke(
        exec_command,
        ["test-agent", "echo hello", "--format", "jsonl"],
        obj=plugin_manager,
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    output = json.loads(result.output.strip())
    assert output["event"] == "exec_result"
    assert output["agent"] == "test-agent"
    assert output["success"] is True
