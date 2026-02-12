from pathlib import Path
from typing import Final

import pluggy
import pytest
from click.testing import CliRunner

import imbue.mngr.cli.bootstrap as bootstrap_module
from imbue.mngr.cli.bootstrap import _build_system_prompt
from imbue.mngr.cli.bootstrap import _get_default_dockerfile
from imbue.mngr.cli.bootstrap import _resolve_output_path
from imbue.mngr.cli.bootstrap import _strip_non_dockerfile_content
from imbue.mngr.cli.bootstrap import bootstrap
from imbue.mngr.cli.conftest import FakeClaudeBackend
from imbue.mngr.cli.conftest import FakeClaudeBackendError

_FAKE_DOCKERFILE: Final[str] = "FROM python:3.11-slim\nRUN apt-get update\n"


@pytest.fixture
def fake_claude(monkeypatch: pytest.MonkeyPatch) -> FakeClaudeBackend:
    """Provide a FakeClaudeBackend and monkeypatch it into the bootstrap module."""
    backend = FakeClaudeBackend()
    monkeypatch.setattr(bootstrap_module, "SubprocessClaudeBackend", lambda **_kwargs: backend)
    return backend


# =============================================================================
# _build_system_prompt tests
# =============================================================================


def test_build_system_prompt_contains_required_tools() -> None:
    """The system prompt should mention mngr-required tools."""
    prompt = _build_system_prompt("FROM python:3.11-slim\nRUN apt-get update\n")

    assert "openssh-server" in prompt
    assert "tmux" in prompt
    assert "git" in prompt
    assert "ripgrep" in prompt
    assert "uv" in prompt
    assert "Claude Code" in prompt


def test_build_system_prompt_contains_reference_dockerfile() -> None:
    """The system prompt should include the default Dockerfile as reference."""
    default_dockerfile = "FROM python:3.11-slim\nRUN apt-get update\n"
    prompt = _build_system_prompt(default_dockerfile)

    assert default_dockerfile in prompt


def test_build_system_prompt_instructs_agentic_exploration() -> None:
    """The system prompt should instruct Claude to use Read/Glob/Grep tools."""
    prompt = _build_system_prompt("FROM python:3.11-slim\n")

    assert "Read" in prompt
    assert "Glob" in prompt
    assert "Grep" in prompt
    assert "explore" in prompt.lower()


# =============================================================================
# _get_default_dockerfile tests
# =============================================================================


def test_get_default_dockerfile_returns_non_empty_content() -> None:
    """The default Dockerfile resource should be non-empty."""
    content = _get_default_dockerfile()
    assert len(content) > 0
    assert "FROM" in content


# =============================================================================
# _resolve_output_path tests
# =============================================================================


def test_resolve_output_path_default(tmp_path: Path) -> None:
    """Default path should be project_dir/.mngr/Dockerfile."""
    result = _resolve_output_path(tmp_path, None)
    assert result == tmp_path / ".mngr" / "Dockerfile"


def test_resolve_output_path_override(tmp_path: Path) -> None:
    """Override should return the specified path."""
    result = _resolve_output_path(tmp_path, "/custom/path/Dockerfile")
    assert result == Path("/custom/path/Dockerfile")


# =============================================================================
# _strip_non_dockerfile_content tests
# =============================================================================


def test_strip_non_dockerfile_content_removes_fences() -> None:
    content = "```dockerfile\nFROM python:3.11\nRUN echo hello\n```"
    assert _strip_non_dockerfile_content(content) == "FROM python:3.11\nRUN echo hello"


def test_strip_non_dockerfile_content_no_fences() -> None:
    content = "FROM python:3.11\nRUN echo hello"
    assert _strip_non_dockerfile_content(content) == content


def test_strip_non_dockerfile_content_removes_preamble() -> None:
    """Explanatory text before the first FROM line should be stripped."""
    content = "Let me explore the project first.\nHere is the Dockerfile:\nFROM python:3.11\nRUN echo hello"
    assert _strip_non_dockerfile_content(content) == "FROM python:3.11\nRUN echo hello"


def test_strip_non_dockerfile_content_returns_empty_when_no_from() -> None:
    """Content without a FROM instruction should return empty string."""
    content = "I'm sorry, I cannot generate a Dockerfile for this project."
    assert _strip_non_dockerfile_content(content) == ""


# =============================================================================
# CLI integration tests
# =============================================================================


def test_bootstrap_writes_dockerfile(
    fake_claude: FakeClaudeBackend,
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
    tmp_path: Path,
) -> None:
    """The bootstrap command should write a Dockerfile to .mngr/Dockerfile."""
    fake_claude.responses.append(_FAKE_DOCKERFILE)
    project_dir = tmp_path / "project"
    project_dir.mkdir()

    result = cli_runner.invoke(
        bootstrap,
        ["--project-dir", str(project_dir)],
        obj=plugin_manager,
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    output_file = project_dir / ".mngr" / "Dockerfile"
    assert output_file.exists()
    written_content = output_file.read_text()
    assert "FROM python:3.11-slim" in written_content


def test_bootstrap_dry_run_does_not_write(
    fake_claude: FakeClaudeBackend,
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
    tmp_path: Path,
) -> None:
    """Dry run should print to stdout and not write any file."""
    fake_claude.responses.append(_FAKE_DOCKERFILE)
    project_dir = tmp_path / "project"
    project_dir.mkdir()

    result = cli_runner.invoke(
        bootstrap,
        ["--dry-run", "--project-dir", str(project_dir)],
        obj=plugin_manager,
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert "FROM python:3.11-slim" in result.output
    assert not (project_dir / ".mngr" / "Dockerfile").exists()


def test_bootstrap_force_overwrites_existing(
    fake_claude: FakeClaudeBackend,
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
    tmp_path: Path,
) -> None:
    """--force should overwrite an existing Dockerfile."""
    fake_claude.responses.append(_FAKE_DOCKERFILE)
    project_dir = tmp_path / "project"
    mngr_dir = project_dir / ".mngr"
    mngr_dir.mkdir(parents=True)
    existing = mngr_dir / "Dockerfile"
    existing.write_text("OLD CONTENT")

    result = cli_runner.invoke(
        bootstrap,
        ["--force", "--project-dir", str(project_dir)],
        obj=plugin_manager,
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert "FROM python:3.11-slim" in existing.read_text()


def test_bootstrap_refuses_overwrite_without_force(
    fake_claude: FakeClaudeBackend,
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
    tmp_path: Path,
) -> None:
    """Should fail if Dockerfile exists and --force is not specified."""
    fake_claude.responses.append(_FAKE_DOCKERFILE)
    project_dir = tmp_path / "project"
    mngr_dir = project_dir / ".mngr"
    mngr_dir.mkdir(parents=True)
    (mngr_dir / "Dockerfile").write_text("OLD CONTENT")

    result = cli_runner.invoke(
        bootstrap,
        ["--project-dir", str(project_dir)],
        obj=plugin_manager,
        catch_exceptions=True,
    )

    assert result.exit_code != 0
    assert "already exists" in result.output


def test_bootstrap_json_output(
    fake_claude: FakeClaudeBackend,
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
    tmp_path: Path,
) -> None:
    """JSON format should emit a JSON object with the dockerfile content."""
    fake_claude.responses.append(_FAKE_DOCKERFILE)
    project_dir = tmp_path / "project"
    project_dir.mkdir()

    result = cli_runner.invoke(
        bootstrap,
        ["--format", "json", "--dry-run", "--project-dir", str(project_dir)],
        obj=plugin_manager,
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert '"dockerfile"' in result.output


def test_bootstrap_jsonl_output(
    fake_claude: FakeClaudeBackend,
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
    tmp_path: Path,
) -> None:
    """JSONL format should emit a JSONL event with the dockerfile content."""
    fake_claude.responses.append(_FAKE_DOCKERFILE)
    project_dir = tmp_path / "project"
    project_dir.mkdir()

    result = cli_runner.invoke(
        bootstrap,
        ["--format", "jsonl", "--dry-run", "--project-dir", str(project_dir)],
        obj=plugin_manager,
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert '"event": "dockerfile"' in result.output


def test_bootstrap_claude_error_shows_message(
    monkeypatch: pytest.MonkeyPatch,
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
    tmp_path: Path,
) -> None:
    """When Claude fails, the error should be displayed to the user."""
    backend = FakeClaudeBackendError(error_message="claude failed (exit code 1): auth error")
    monkeypatch.setattr(bootstrap_module, "SubprocessClaudeBackend", lambda **_kwargs: backend)
    project_dir = tmp_path / "project"
    project_dir.mkdir()

    result = cli_runner.invoke(
        bootstrap,
        ["--project-dir", str(project_dir)],
        obj=plugin_manager,
        catch_exceptions=True,
    )

    assert result.exit_code != 0
    assert "auth error" in result.output


def test_bootstrap_empty_response_shows_error(
    fake_claude: FakeClaudeBackend,
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
    tmp_path: Path,
) -> None:
    """An empty response from Claude should produce a clear error."""
    fake_claude.responses.append("")
    project_dir = tmp_path / "project"
    project_dir.mkdir()

    result = cli_runner.invoke(
        bootstrap,
        ["--project-dir", str(project_dir)],
        obj=plugin_manager,
        catch_exceptions=True,
    )

    assert result.exit_code != 0
    assert "empty response" in result.output


def test_bootstrap_empty_fences_response_shows_error(
    fake_claude: FakeClaudeBackend,
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
    tmp_path: Path,
) -> None:
    """A response with only empty markdown fences should produce a clear error."""
    fake_claude.responses.append("```dockerfile\n```")
    project_dir = tmp_path / "project"
    project_dir.mkdir()

    result = cli_runner.invoke(
        bootstrap,
        ["--project-dir", str(project_dir)],
        obj=plugin_manager,
        catch_exceptions=True,
    )

    assert result.exit_code != 0
    assert "did not contain valid Dockerfile content" in result.output


def test_bootstrap_creates_mngr_directory(
    fake_claude: FakeClaudeBackend,
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
    tmp_path: Path,
) -> None:
    """The .mngr directory should be created if it doesn't exist."""
    fake_claude.responses.append(_FAKE_DOCKERFILE)
    project_dir = tmp_path / "project"
    project_dir.mkdir()

    result = cli_runner.invoke(
        bootstrap,
        ["--project-dir", str(project_dir)],
        obj=plugin_manager,
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert (project_dir / ".mngr").is_dir()
    assert (project_dir / ".mngr" / "Dockerfile").is_file()


def test_bootstrap_strips_markdown_fences_from_response(
    fake_claude: FakeClaudeBackend,
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
    tmp_path: Path,
) -> None:
    """Markdown fences in Claude's response should be stripped."""
    fake_claude.responses.append("```dockerfile\nFROM python:3.11-slim\n```")
    project_dir = tmp_path / "project"
    project_dir.mkdir()

    result = cli_runner.invoke(
        bootstrap,
        ["--project-dir", str(project_dir)],
        obj=plugin_manager,
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    content = (project_dir / ".mngr" / "Dockerfile").read_text()
    assert "```" not in content
    assert "FROM python:3.11-slim" in content
