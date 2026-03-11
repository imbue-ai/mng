import json
from collections.abc import Iterator
from pathlib import Path

import pluggy
import pytest
from click.testing import CliRunner

import imbue.mng.cli.ask as ask_module
from imbue.mng.cli.ask import ClaudeBackendInterface
from imbue.mng.cli.ask import _accumulate_chunks
from imbue.mng.cli.ask import _build_ask_context
from imbue.mng.cli.ask import _build_read_only_tools_and_permissions
from imbue.mng.cli.ask import _build_source_access_context
from imbue.mng.cli.ask import _build_web_access_context
from imbue.mng.cli.ask import _execute_response
from imbue.mng.cli.ask import _find_mng_source_directory
from imbue.mng.cli.ask import _run_ask_query
from imbue.mng.cli.ask import _show_command_summary
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
def fake_claude(monkeypatch: pytest.MonkeyPatch) -> FakeClaude:
    """Provide a FakeClaude backend and monkeypatch it into the ask module."""
    backend = FakeClaude()
    monkeypatch.setattr(ask_module, "HeadlessClaudeBackend", lambda **kwargs: backend)
    return backend


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
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """The full query (with prefix) should be passed to the claude backend."""
    fake_claude.responses.append("mng create my-agent")

    result = cli_runner.invoke(
        ask, ["how", "do", "I", "create", "an", "agent?"], obj=plugin_manager, catch_exceptions=False
    )

    assert result.exit_code == 0
    assert "mng create my-agent" in result.output
    assert len(fake_claude.queries) == 1
    assert "how do I create an agent?" in fake_claude.queries[0]


def test_ask_json_output(
    fake_claude: FakeClaude,
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    fake_claude.responses.append("mng list")

    result = cli_runner.invoke(ask, ["--format", "json", "list", "agents"], obj=plugin_manager, catch_exceptions=False)

    assert result.exit_code == 0
    assert '"response": "mng list"' in result.output


def test_ask_jsonl_output(
    fake_claude: FakeClaude,
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    fake_claude.responses.append("mng list")

    result = cli_runner.invoke(
        ask, ["--format", "jsonl", "list", "agents"], obj=plugin_manager, catch_exceptions=False
    )

    assert result.exit_code == 0
    assert '"event": "response"' in result.output
    assert '"response": "mng list"' in result.output


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
def test_ask_claude_error_shows_message(
    error_message: str,
    expected_substring: str,
    monkeypatch: pytest.MonkeyPatch,
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """When the claude backend raises an error, it should be displayed to the user."""
    backend = FakeClaudeError(error_message=error_message)
    monkeypatch.setattr(ask_module, "HeadlessClaudeBackend", lambda **kwargs: backend)

    result = cli_runner.invoke(ask, ["test"], obj=plugin_manager, catch_exceptions=True)

    assert result.exit_code != 0
    assert expected_substring in result.output


def test_ask_human_streams_output(
    fake_claude: FakeClaude,
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """HUMAN format should output the streamed response text."""
    fake_claude.responses.append("Use mng create")

    result = cli_runner.invoke(ask, ["how", "to", "create?"], obj=plugin_manager, catch_exceptions=False)

    assert result.exit_code == 0
    assert "Use mng create" in result.output


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


# =============================================================================
# Tests for _accumulate_chunks
# =============================================================================


def test_accumulate_chunks_joins_all_chunks() -> None:
    """_accumulate_chunks should join all chunks into a single string."""
    chunks = iter(["Hello ", "world", "!"])
    result = _accumulate_chunks(chunks)
    assert result == "Hello world!"


def test_accumulate_chunks_empty_iterator() -> None:
    """_accumulate_chunks should return empty string for empty iterator."""
    chunks = iter([])
    result = _accumulate_chunks(chunks)
    assert result == ""


def test_accumulate_chunks_single_chunk() -> None:
    """_accumulate_chunks should work with a single chunk."""
    chunks = iter(["Hello"])
    result = _accumulate_chunks(chunks)
    assert result == "Hello"


# =============================================================================
# Tests for _show_command_summary
# =============================================================================


def test_show_command_summary_human(capsys: pytest.CaptureFixture[str]) -> None:
    """_show_command_summary should output command list in HUMAN format."""
    _show_command_summary(OutputFormat.HUMAN)
    captured = capsys.readouterr()
    assert "Available mng commands" in captured.out
    assert "mng ask" in captured.out


def test_show_command_summary_json(capsys: pytest.CaptureFixture[str]) -> None:
    """_show_command_summary should output JSON in JSON format."""
    _show_command_summary(OutputFormat.JSON)
    captured = capsys.readouterr()
    data = json.loads(captured.out.strip())
    assert "commands" in data


def test_show_command_summary_jsonl(capsys: pytest.CaptureFixture[str]) -> None:
    """_show_command_summary should output JSONL in JSONL format."""
    _show_command_summary(OutputFormat.JSONL)
    captured = capsys.readouterr()
    data = json.loads(captured.out.strip())
    assert data["event"] == "commands"


# =============================================================================
# Tests for _find_mng_source_directory
# =============================================================================


def test_find_mng_source_directory_returns_path() -> None:
    """Should find the mng source directory when running from the source tree."""
    result = _find_mng_source_directory()
    assert result is not None
    assert (result / "imbue" / "mng").is_dir()


def test_find_mng_source_directory_returns_none_when_not_found(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Should return None when the source tree is not found."""
    fake_file = tmp_path / "a" / "b" / "c" / "ask.py"
    fake_file.parent.mkdir(parents=True)
    fake_file.touch()
    monkeypatch.setattr(ask_module, "__file__", str(fake_file))
    result = _find_mng_source_directory()
    assert result is None


# =============================================================================
# Tests for _build_source_access_context
# =============================================================================


def test_build_source_access_context_contains_key_info(tmp_path: Path) -> None:
    """Should include the source directory path and key directories."""
    (tmp_path / "imbue" / "mng" / "cli").mkdir(parents=True)
    (tmp_path / "docs").mkdir()
    context = _build_source_access_context(tmp_path)
    assert str(tmp_path) in context
    assert "Source Code Access" in context
    assert "docs/" in context
    assert "imbue/mng/" in context


def test_build_source_access_context_omits_docs_when_missing(tmp_path: Path) -> None:
    """Should omit docs directory reference when docs/ does not exist."""
    (tmp_path / "imbue" / "mng").mkdir(parents=True)
    context = _build_source_access_context(tmp_path)
    assert "docs/" not in context


# =============================================================================
# Tests for _build_web_access_context
# =============================================================================


def test_build_web_access_context_contains_github_info() -> None:
    """Should include GitHub repository reference."""
    context = _build_web_access_context()
    assert "Web Access" in context
    assert "github.com/imbue-ai/mng" in context
    assert "WebFetch" in context


# =============================================================================
# Tests for _build_read_only_tools_and_permissions
# =============================================================================


def test_build_tools_with_source_directory_scopes_read_tools(tmp_path: Path) -> None:
    """Read/Glob/Grep should be included and path-scoped to source_directory."""
    tools, args = _build_read_only_tools_and_permissions(tmp_path, allow_web=False)
    assert tools == "Read,Glob,Grep"
    assert f"Read(//{tmp_path}/**)" in args
    assert f"Glob(//{tmp_path}/**)" in args
    assert f"Grep(//{tmp_path}/**)" in args


def test_build_tools_without_source_directory_excludes_read_tools() -> None:
    """When source_directory is None, no Read/Glob/Grep tools should be included."""
    tools, args = _build_read_only_tools_and_permissions(None, allow_web=False)
    assert tools == ""
    assert args == ()


def test_build_tools_with_web_includes_webfetch() -> None:
    """WebFetch should be included and domain-scoped when allow_web is True."""
    tools, args = _build_read_only_tools_and_permissions(None, allow_web=True)
    assert tools == "WebFetch"
    assert "WebFetch(domain:github.com)" in args
    assert "WebFetch(domain:raw.githubusercontent.com)" in args


def test_build_tools_with_source_and_web_includes_all(tmp_path: Path) -> None:
    """Both read tools and WebFetch should be included when both are enabled."""
    tools, args = _build_read_only_tools_and_permissions(tmp_path, allow_web=True)
    assert "Read,Glob,Grep" in tools
    assert "WebFetch" in tools
    assert f"Read(//{tmp_path}/**)" in args
    assert "WebFetch(domain:github.com)" in args


# =============================================================================
# Tests for _run_ask_query
# =============================================================================


def test_run_ask_query_includes_source_context() -> None:
    """System prompt should include source access context when source directory exists."""
    source_dir = _find_mng_source_directory()
    assert source_dir is not None
    backend = FakeClaude(responses=["mng list"])
    _run_ask_query(
        backend=backend,
        query_string="test query",
        source_directory=source_dir,
        execute=False,
        allow_web=False,
        output_format=OutputFormat.HUMAN,
    )
    assert len(backend.system_prompts) == 1
    assert "Source Code Access" in backend.system_prompts[0]


def test_run_ask_query_excludes_source_context_when_none() -> None:
    """System prompt should not include source access context when source_directory is None."""
    backend = FakeClaude(responses=["mng list"])
    _run_ask_query(
        backend=backend,
        query_string="test query",
        source_directory=None,
        execute=False,
        allow_web=False,
        output_format=OutputFormat.HUMAN,
    )
    assert len(backend.system_prompts) == 1
    assert "Source Code Access" not in backend.system_prompts[0]


def test_run_ask_query_includes_web_context_when_enabled() -> None:
    """System prompt should include web access context when allow_web is True."""
    backend = FakeClaude(responses=["mng list"])
    _run_ask_query(
        backend=backend,
        query_string="test query",
        source_directory=None,
        execute=False,
        allow_web=True,
        output_format=OutputFormat.HUMAN,
    )
    assert len(backend.system_prompts) == 1
    assert "Web Access" in backend.system_prompts[0]


def test_run_ask_query_excludes_web_context_when_disabled() -> None:
    """System prompt should not include web access context when allow_web is False."""
    backend = FakeClaude(responses=["mng list"])
    _run_ask_query(
        backend=backend,
        query_string="test query",
        source_directory=None,
        execute=False,
        allow_web=False,
        output_format=OutputFormat.HUMAN,
    )
    assert len(backend.system_prompts) == 1
    assert "Web Access" not in backend.system_prompts[0]


def test_ask_with_allow_web_flag(
    fake_claude: FakeClaude,
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """The --allow-web flag should be accepted without error."""
    fake_claude.responses.append("mng list")
    result = cli_runner.invoke(
        ask, ["--allow-web", "how", "to", "list?"], obj=plugin_manager, catch_exceptions=False
    )
    assert result.exit_code == 0
    assert "mng list" in result.output
