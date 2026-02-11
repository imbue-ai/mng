import subprocess
from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock
from unittest.mock import patch

import pluggy
import pytest
from click.testing import CliRunner

from imbue.mngr.cli.ask import _build_ask_context
from imbue.mngr.cli.ask import _emit_response
from imbue.mngr.cli.ask import _execute_response
from imbue.mngr.cli.ask import ask
from imbue.mngr.errors import MngrError
from imbue.mngr.primitives import OutputFormat

_real_subprocess_run = subprocess.run


def _mock_subprocess(
    responses: list[subprocess.CompletedProcess],
    intercept: tuple[str, ...] = ("claude",),
) -> Callable:
    """Create a subprocess.run wrapper that intercepts specific commands.

    Commands whose first argument is in `intercept` return canned responses.
    All other calls (git, etc.) pass through to the real subprocess.run.
    """
    call_index = 0

    def side_effect(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
        nonlocal call_index
        if isinstance(cmd, list) and cmd[0] in intercept:
            result = responses[call_index]
            call_index += 1
            return result
        return _real_subprocess_run(cmd, **kwargs)

    return side_effect


def test_build_ask_context_contains_mngr_docs() -> None:
    """The generated context should contain mngr command documentation from the registry."""
    context = _build_ask_context()
    assert len(context) > 100
    assert "mngr" in context
    assert "create" in context.lower()


def test_no_query_shows_command_summary(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """When no query is provided, shows a summary of available commands."""
    result = cli_runner.invoke(ask, [], obj=plugin_manager, catch_exceptions=False)
    assert result.exit_code == 0
    assert "Available mngr commands" in result.output
    assert "mngr ask" in result.output


@patch("imbue.mngr.cli.ask.subprocess.run")
def test_ask_passes_query_to_claude(
    mock_run: MagicMock,
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """The full query (with prefix) should be passed as an arg to claude --print."""
    mock_run.side_effect = _mock_subprocess(
        [
            subprocess.CompletedProcess(args=[], returncode=0, stdout="mngr create my-agent\n", stderr=""),
        ]
    )

    result = cli_runner.invoke(
        ask, ["how", "do", "I", "create", "an", "agent?"], obj=plugin_manager, catch_exceptions=False
    )

    assert result.exit_code == 0
    assert "mngr create my-agent" in result.output

    claude_calls = [c for c in mock_run.call_args_list if c[0][0][0] == "claude"]
    assert len(claude_calls) == 1
    call_args = claude_calls[0][0][0]
    assert "--print" in call_args
    assert "--system-prompt" in call_args
    assert "how do I create an agent?" in call_args[-1]


@patch("imbue.mngr.cli.ask.subprocess.run")
def test_ask_json_output(
    mock_run: MagicMock,
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    mock_run.side_effect = _mock_subprocess(
        [
            subprocess.CompletedProcess(args=[], returncode=0, stdout="mngr list\n", stderr=""),
        ]
    )

    result = cli_runner.invoke(ask, ["--format", "json", "list", "agents"], obj=plugin_manager, catch_exceptions=False)

    assert result.exit_code == 0
    assert '"response": "mngr list"' in result.output


@patch("imbue.mngr.cli.ask.subprocess.run")
def test_ask_runs_from_temp_dir(
    mock_run: MagicMock,
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Claude should be invoked from a temp dir, not the user's cwd."""
    mock_run.side_effect = _mock_subprocess(
        [
            subprocess.CompletedProcess(args=[], returncode=0, stdout="ok\n", stderr=""),
        ]
    )

    cli_runner.invoke(ask, ["test"], obj=plugin_manager, catch_exceptions=False)

    claude_calls = [c for c in mock_run.call_args_list if c[0][0][0] == "claude"]
    cwd = claude_calls[0][1]["cwd"]
    assert "mngr-ask-" in cwd


@patch("imbue.mngr.cli.ask.subprocess.run")
def test_ask_claude_failure_shows_error(
    mock_run: MagicMock,
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    mock_run.side_effect = _mock_subprocess(
        [
            subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="authentication failed"),
        ]
    )

    result = cli_runner.invoke(ask, ["test"], obj=plugin_manager, catch_exceptions=True)

    assert result.exit_code != 0
    assert "authentication failed" in result.output


@patch("imbue.mngr.cli.ask.subprocess.run")
def test_ask_execute_mode_runs_generated_command(
    mock_run: MagicMock,
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """--execute should first call claude, then run the generated command."""
    mock_run.side_effect = _mock_subprocess(
        [
            subprocess.CompletedProcess(args=[], returncode=0, stdout="mngr list\n", stderr=""),
            subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
        ],
        intercept=("claude", "mngr"),
    )

    result = cli_runner.invoke(ask, ["--execute", "list", "my", "agents"], obj=plugin_manager, catch_exceptions=False)

    assert result.exit_code == 0
    intercepted = [
        c for c in mock_run.call_args_list if isinstance(c[0][0], list) and c[0][0][0] in ("claude", "mngr")
    ]
    assert len(intercepted) == 2
    assert intercepted[0][0][0][0] == "claude"
    assert intercepted[1][0][0] == ["mngr", "list"]


@patch("imbue.mngr.cli.ask.subprocess.run")
def test_ask_execute_uses_execute_prefix(
    mock_run: MagicMock,
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """--execute mode should use the execute-specific prompt prefix."""
    mock_run.side_effect = _mock_subprocess(
        [
            subprocess.CompletedProcess(args=[], returncode=0, stdout="mngr list\n", stderr=""),
            subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
        ],
        intercept=("claude", "mngr"),
    )

    cli_runner.invoke(ask, ["--execute", "list", "agents"], obj=plugin_manager, catch_exceptions=False)

    claude_calls = [c for c in mock_run.call_args_list if isinstance(c[0][0], list) and c[0][0][0] == "claude"]
    query_arg = claude_calls[0][0][0][-1]
    assert "executed directly" in query_arg


def test_emit_response_json_format(capsys: pytest.CaptureFixture) -> None:
    _emit_response(response="Use mngr create", output_format=OutputFormat.JSON)
    captured = capsys.readouterr()
    assert '"response": "Use mngr create"' in captured.out


def test_emit_response_jsonl_format(capsys: pytest.CaptureFixture) -> None:
    _emit_response(response="Use mngr create", output_format=OutputFormat.JSONL)
    captured = capsys.readouterr()
    assert '"event": "response"' in captured.out
    assert '"response": "Use mngr create"' in captured.out


def test_execute_response_raises_on_empty_response() -> None:
    with pytest.raises(MngrError, match="empty response"):
        _execute_response(response="   \n  ", output_format=OutputFormat.HUMAN)


def test_execute_response_rejects_non_mngr_command() -> None:
    """Commands that don't start with 'mngr' should be rejected."""
    with pytest.raises(MngrError, match="not a valid mngr command"):
        _execute_response(response="rm -rf /", output_format=OutputFormat.HUMAN)


def test_execute_response_rejects_markdown_response() -> None:
    """Markdown-wrapped responses should be rejected."""
    with pytest.raises(MngrError, match="not a valid mngr command"):
        _execute_response(response="```\nmngr list\n```", output_format=OutputFormat.HUMAN)


@patch("imbue.mngr.cli.ask.subprocess.run")
def test_ask_claude_not_installed(
    mock_run: MagicMock,
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """When claude binary is missing, show a helpful error message."""

    def raise_fnf(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
        if isinstance(cmd, list) and cmd[0] == "claude":
            raise FileNotFoundError("No such file or directory: 'claude'")
        return _real_subprocess_run(cmd, **kwargs)

    mock_run.side_effect = raise_fnf

    result = cli_runner.invoke(ask, ["test"], obj=plugin_manager, catch_exceptions=True)

    assert result.exit_code != 0
    assert "claude is not installed" in result.output


def test_no_query_json_output(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """No-query with JSON format should emit commands dict."""
    result = cli_runner.invoke(ask, ["--format", "json"], obj=plugin_manager, catch_exceptions=False)
    assert result.exit_code == 0
    assert '"commands"' in result.output
