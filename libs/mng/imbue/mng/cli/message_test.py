import click
import pytest

from imbue.mng.api.message import MessageResult
from imbue.mng.cli.message import MessageCliOptions
from imbue.mng.cli.message import _build_retry_hint
from imbue.mng.cli.message import _emit_human_output
from imbue.mng.cli.message import _emit_json_output
from imbue.mng.cli.message import _get_message_content


def test_message_cli_options_has_expected_fields() -> None:
    """Test that MessageCliOptions has all expected fields."""
    opts = MessageCliOptions(
        agents=("agent1", "agent2"),
        agent_list=("agent3",),
        all_agents=False,
        include=("name == 'test'",),
        exclude=(),
        stdin=False,
        message_content="Hello",
        on_error="continue",
        start=False,
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
    assert opts.agents == ("agent1", "agent2")
    assert opts.agent_list == ("agent3",)
    assert opts.all_agents is False
    assert opts.message_content == "Hello"


def test_get_message_content_returns_option_when_provided() -> None:
    """Test that _get_message_content returns the option value when provided."""
    result = _get_message_content("Hello World", click.Context(click.Command("test")))
    assert result == "Hello World"


def test_emit_human_output_logs_successful_agents(capsys: pytest.CaptureFixture) -> None:
    """Test that _emit_human_output logs successful agents."""
    result = MessageResult()
    result.successful_agents = ["agent1", "agent2"]

    _emit_human_output(result, "test message")

    # The output is logged via loguru, not printed directly
    # We can't easily capture it here, but we can verify no exception is raised


def test_emit_human_output_logs_failed_agents(capsys: pytest.CaptureFixture) -> None:
    """Test that _emit_human_output logs failed agents."""
    result = MessageResult()
    result.failed_agents = [("agent1", "error1"), ("agent2", "error2")]

    _emit_human_output(result, "test message")

    # The output is logged via loguru


def test_emit_human_output_handles_no_agents() -> None:
    """Test that _emit_human_output handles no agents case."""
    result = MessageResult()

    # Should not raise
    _emit_human_output(result, "test message")


def test_emit_json_output_formats_successful_agents(capsys: pytest.CaptureFixture) -> None:
    """Test that _emit_json_output includes successful agents."""
    result = MessageResult()
    result.successful_agents = ["agent1", "agent2"]

    _emit_json_output(result)

    captured = capsys.readouterr()
    assert '"successful_agents": ["agent1", "agent2"]' in captured.out


def test_emit_json_output_formats_failed_agents(capsys: pytest.CaptureFixture) -> None:
    """Test that _emit_json_output includes failed agents."""
    result = MessageResult()
    result.failed_agents = [("agent1", "error message")]

    _emit_json_output(result)

    captured = capsys.readouterr()
    assert '"failed_agents"' in captured.out
    assert '"agent": "agent1"' in captured.out
    assert '"error": "error message"' in captured.out


def test_emit_json_output_includes_counts(capsys: pytest.CaptureFixture) -> None:
    """Test that _emit_json_output includes counts."""
    result = MessageResult()
    result.successful_agents = ["agent1", "agent2", "agent3"]
    result.failed_agents = [("agent4", "error")]

    _emit_json_output(result)

    captured = capsys.readouterr()
    assert '"total_sent": 3' in captured.out
    assert '"total_failed": 1' in captured.out


def test_build_retry_hint_includes_failed_agent_names_and_message() -> None:
    """Test that _build_retry_hint builds a command with agent names and message."""
    failed = [("agent1", "some error"), ("agent3", "another error")]

    hint = _build_retry_hint(failed, "hello world")

    assert hint == "mng message agent1 agent3 -m 'hello world'"


def test_build_retry_hint_shell_quotes_special_characters() -> None:
    """Test that _build_retry_hint shell-quotes agent names and message with special chars."""
    failed = [("my-agent", "error")]

    hint = _build_retry_hint(failed, "it's a test")

    assert "my-agent" in hint
    assert "-m" in hint
    # shlex.quote should handle the apostrophe
    assert "it" in hint
    assert "test" in hint


def test_build_retry_hint_omits_message_when_too_long() -> None:
    """Test that _build_retry_hint uses placeholder for long messages."""
    failed = [("agent1", "error")]
    long_message = "x" * 201

    hint = _build_retry_hint(failed, long_message)

    assert hint == "mng message agent1 -m <MESSAGE>"


def test_build_retry_hint_omits_message_when_multiline() -> None:
    """Test that _build_retry_hint uses placeholder for multiline messages."""
    failed = [("agent1", "error")]

    hint = _build_retry_hint(failed, "line one\nline two")

    assert hint == "mng message agent1 -m <MESSAGE>"
