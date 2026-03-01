import json
from collections.abc import Iterator
from pathlib import Path

import pluggy
import pytest
from click.testing import CliRunner

from imbue.mng.cli.ask import ClaudeBackendInterface
from imbue.mng.cli.ask import _build_ask_context
from imbue.mng.cli.ask import _build_source_access_context
from imbue.mng.cli.ask import _build_web_access_context
from imbue.mng.cli.ask import _execute_response
from imbue.mng.cli.ask import _extract_text_delta
from imbue.mng.cli.ask import _find_mng_source_directory
from imbue.mng.cli.ask import _run_ask_query
from imbue.mng.cli.ask import ask
from imbue.mng.errors import MngError
from imbue.mng.primitives import OutputFormat


class FakeClaude(ClaudeBackendInterface):
    """Test double that records queries and returns canned responses."""

    responses: list[str] = []
    queries: list[str] = []
    system_prompts: list[str] = []

    def query(self, prompt: str, system_prompt: str) -> Iterator[str]:
        self.queries.append(prompt)
        self.system_prompts.append(system_prompt)
        yield self.responses.pop(0)


class FakeClaudeError(ClaudeBackendInterface):
    """Test double that raises MngError on query."""

    error_message: str

    def query(self, prompt: str, system_prompt: str) -> Iterator[str]:
        raise MngError(self.error_message)


@pytest.fixture
def fake_claude() -> FakeClaude:
    """Provide a FakeClaude backend for direct use with _run_ask_query."""
    return FakeClaude()


def test_build_ask_context_contains_mng_docs() -> None:
    """The generated context should contain mng command documentation from the registry."""
    context = _build_ask_context()
    assert len(context) > 100
    assert "mng" in context
    assert "create" in context.lower()


def test_no_query_shows_command_summary(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """When no query is provided, shows a summary of available commands."""
    result = cli_runner.invoke(ask, [], obj=plugin_manager, catch_exceptions=False)
    assert result.exit_code == 0
    assert "Available mng commands" in result.output
    assert "mng ask" in result.output


def test_ask_passes_query_to_claude(
    fake_claude: FakeClaude,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The query should be passed to the claude backend."""
    fake_claude.responses.append("mng create my-agent")

    _run_ask_query(
        backend=fake_claude,
        query_string="how do I create an agent?",
        execute=False,
        allow_web=False,
        output_format=OutputFormat.HUMAN,
    )

    assert len(fake_claude.queries) == 1
    assert "how do I create an agent?" in fake_claude.queries[0]
    captured = capsys.readouterr()
    assert "mng create my-agent" in captured.out


def test_ask_json_output(
    fake_claude: FakeClaude,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake_claude.responses.append("mng list")

    _run_ask_query(
        backend=fake_claude,
        query_string="list agents",
        execute=False,
        allow_web=False,
        output_format=OutputFormat.JSON,
    )

    captured = capsys.readouterr()
    assert '"response": "mng list"' in captured.out


def test_ask_jsonl_output(
    fake_claude: FakeClaude,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake_claude.responses.append("mng list")

    _run_ask_query(
        backend=fake_claude,
        query_string="list agents",
        execute=False,
        allow_web=False,
        output_format=OutputFormat.JSONL,
    )

    captured = capsys.readouterr()
    assert '"event": "response"' in captured.out
    assert '"response": "mng list"' in captured.out


@pytest.mark.parametrize(
    "error_message, expected_substring",
    [
        ("claude --print failed (exit code 1): authentication failed", "authentication failed"),
        (
            "claude is not installed or not found in PATH. Install Claude Code: https://docs.anthropic.com/en/docs/claude-code/overview",
            "claude is not installed",
        ),
    ],
)
def test_ask_claude_error_raises(
    error_message: str,
    expected_substring: str,
) -> None:
    """When the claude backend raises an error, it should propagate as MngError."""
    backend = FakeClaudeError(error_message=error_message)

    with pytest.raises(MngError, match=expected_substring):
        _run_ask_query(
            backend=backend,
            query_string="test",
            execute=False,
            allow_web=False,
            output_format=OutputFormat.HUMAN,
        )


def test_ask_human_streams_output(
    fake_claude: FakeClaude,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """HUMAN format should output the streamed response text."""
    fake_claude.responses.append("Use mng create")

    _run_ask_query(
        backend=fake_claude,
        query_string="how to create?",
        execute=False,
        allow_web=False,
        output_format=OutputFormat.HUMAN,
    )

    captured = capsys.readouterr()
    assert "Use mng create" in captured.out


def test_extract_text_delta_valid_event() -> None:
    """A valid content_block_delta event should return the text."""
    event = json.dumps(
        {
            "type": "stream_event",
            "event": {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "text_delta", "text": "hello"},
            },
        }
    )
    assert _extract_text_delta(event) == "hello"


def test_extract_text_delta_non_delta_event() -> None:
    """Non-delta events should return None."""
    event = json.dumps(
        {
            "type": "stream_event",
            "event": {"type": "content_block_start", "index": 0},
        }
    )
    assert _extract_text_delta(event) is None


def test_extract_text_delta_malformed_json() -> None:
    """Malformed JSON should return None, not raise."""
    assert _extract_text_delta("not valid json {{{") is None


def test_extract_text_delta_non_stream_event() -> None:
    """Events that are not stream_event type should return None."""
    event = json.dumps({"type": "result", "subtype": "success"})
    assert _extract_text_delta(event) is None


def test_extract_text_delta_missing_delta() -> None:
    """content_block_delta without a delta field should return None."""
    event = json.dumps(
        {
            "type": "stream_event",
            "event": {"type": "content_block_delta", "index": 0},
        }
    )
    assert _extract_text_delta(event) is None


def test_execute_response_raises_on_empty_response() -> None:
    with pytest.raises(MngError, match="empty response"):
        _execute_response(response="   \n  ", output_format=OutputFormat.HUMAN)


def test_execute_response_rejects_non_mng_command() -> None:
    """Commands that don't start with 'mng' should be rejected."""
    with pytest.raises(MngError, match="not a valid mng command"):
        _execute_response(response="rm -rf /", output_format=OutputFormat.HUMAN)


def test_execute_response_rejects_markdown_response() -> None:
    """Markdown-wrapped responses should be rejected."""
    with pytest.raises(MngError, match="not a valid mng command"):
        _execute_response(response="```\nmng list\n```", output_format=OutputFormat.HUMAN)


def test_execute_response_raises_on_unmatched_quotes() -> None:
    """shlex.split raises ValueError on unmatched quotes; should become MngError."""
    with pytest.raises(MngError, match="could not be parsed"):
        _execute_response(response="mng create 'unmatched", output_format=OutputFormat.HUMAN)


def test_no_query_json_output(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """No-query with JSON format should emit commands dict."""
    result = cli_runner.invoke(ask, ["--format", "json"], obj=plugin_manager, catch_exceptions=False)
    assert result.exit_code == 0
    assert '"commands"' in result.output


def test_find_mng_source_directory_returns_valid_path() -> None:
    """When running from source, should find the project directory with imbue/mng/."""
    source_dir = _find_mng_source_directory()
    assert source_dir is not None
    assert (source_dir / "imbue" / "mng").is_dir()


def test_build_source_access_context_includes_source_directory_and_key_paths() -> None:
    context = _build_source_access_context(Path("/fake/mng/project"))
    assert "/fake/mng/project" in context
    assert "imbue/mng/" in context
    assert "Read" in context
    # docs/ line is only included when the directory exists on disk
    assert "docs/" not in context


def test_ask_system_prompt_includes_source_access_context(
    fake_claude: FakeClaude,
) -> None:
    """The system prompt passed to claude should include source code access info."""
    fake_claude.responses.append("mng list")

    _run_ask_query(
        backend=fake_claude,
        query_string="list agents",
        execute=False,
        allow_web=False,
        output_format=OutputFormat.HUMAN,
    )

    assert len(fake_claude.system_prompts) == 1
    system_prompt = fake_claude.system_prompts[0]
    assert "Source Code Access" in system_prompt
    assert "docs/" in system_prompt


def test_build_web_access_context_includes_repo_url() -> None:
    context = _build_web_access_context()
    assert "github.com/imbue-ai/mng" in context
    assert "WebFetch" in context


def test_ask_without_allow_web_does_not_include_web_context(
    fake_claude: FakeClaude,
) -> None:
    """Without allow_web, the system prompt should not include web access info."""
    fake_claude.responses.append("mng list")

    _run_ask_query(
        backend=fake_claude,
        query_string="list agents",
        execute=False,
        allow_web=False,
        output_format=OutputFormat.HUMAN,
    )

    assert len(fake_claude.system_prompts) == 1
    assert "Web Access" not in fake_claude.system_prompts[0]


def test_ask_with_allow_web_includes_web_context(
    fake_claude: FakeClaude,
) -> None:
    """With allow_web, the system prompt should include web access info."""
    fake_claude.responses.append("mng list")

    _run_ask_query(
        backend=fake_claude,
        query_string="list agents",
        execute=False,
        allow_web=True,
        output_format=OutputFormat.HUMAN,
    )

    assert len(fake_claude.system_prompts) == 1
    system_prompt = fake_claude.system_prompts[0]
    assert "Web Access" in system_prompt
    assert "github.com/imbue-ai/mng" in system_prompt
