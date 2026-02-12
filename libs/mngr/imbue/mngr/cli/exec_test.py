"""Unit tests for the exec CLI command."""

import json
from io import StringIO

import pluggy
import pytest
from click.testing import CliRunner

from imbue.mngr.api.exec import ExecResult
from imbue.mngr.cli.exec import ExecCliOptions
from imbue.mngr.cli.exec import _emit_human_output
from imbue.mngr.cli.exec import _emit_json_output
from imbue.mngr.cli.exec import _emit_jsonl_output
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


def test_emit_human_output_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test human output prints stdout and logs success."""
    captured = StringIO()
    monkeypatch.setattr("sys.stdout", captured)

    result = ExecResult(agent_name="test-agent", stdout="hello world\n", stderr="", success=True)
    _emit_human_output(result)

    assert "hello world" in captured.getvalue()


def test_emit_human_output_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test human output handles failed commands."""
    captured_out = StringIO()
    captured_err = StringIO()
    monkeypatch.setattr("sys.stdout", captured_out)
    monkeypatch.setattr("sys.stderr", captured_err)

    result = ExecResult(agent_name="test-agent", stdout="", stderr="bad command\n", success=False)
    _emit_human_output(result)

    assert "bad command" in captured_err.getvalue()


def test_emit_json_output(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test JSON output format."""
    captured = StringIO()
    monkeypatch.setattr("sys.stdout", captured)

    result = ExecResult(agent_name="test-agent", stdout="hello\n", stderr="", success=True)
    _emit_json_output(result)

    output = json.loads(captured.getvalue().strip())
    assert output["agent"] == "test-agent"
    assert output["stdout"] == "hello\n"
    assert output["stderr"] == ""
    assert output["success"] is True


def test_emit_jsonl_output(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test JSONL output format."""
    captured = StringIO()
    monkeypatch.setattr("sys.stdout", captured)

    result = ExecResult(agent_name="test-agent", stdout="hello\n", stderr="", success=True)
    _emit_jsonl_output(result)

    output = json.loads(captured.getvalue().strip())
    assert output["event"] == "exec_result"
    assert output["agent"] == "test-agent"
    assert output["success"] is True
