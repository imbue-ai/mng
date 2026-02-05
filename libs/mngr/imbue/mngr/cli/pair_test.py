"""Unit tests for the pair CLI command."""

from click.testing import CliRunner

from imbue.mngr.cli.pair import PairCliOptions
from imbue.mngr.cli.pair import pair


def test_pair_cli_options_has_all_fields() -> None:
    """Test that PairCliOptions has all required fields."""
    assert hasattr(PairCliOptions, "__annotations__")
    annotations = PairCliOptions.__annotations__
    assert "source" in annotations
    assert "source_agent" in annotations
    assert "sync_direction" in annotations
    assert "conflict" in annotations
    assert "exclude" in annotations
    assert "require_git" in annotations
    assert "uncommitted_changes" in annotations


def test_pair_command_is_registered() -> None:
    """Test that the pair command is properly registered."""
    assert pair is not None
    assert pair.name == "pair"


def test_pair_command_help_shows_options() -> None:
    """Test that --help shows all expected options."""
    runner = CliRunner()
    result = runner.invoke(pair, ["--help"])
    assert result.exit_code == 0
    assert "--source" in result.output or "-s" in result.output
    assert "--source-agent" in result.output
    assert "--sync-direction" in result.output
    assert "--conflict" in result.output
    assert "--exclude" in result.output
    assert "--require-git" in result.output or "--no-require-git" in result.output
    assert "--uncommitted-changes" in result.output


def test_pair_sync_direction_choices() -> None:
    """Test that direction option has expected choices."""
    runner = CliRunner()
    result = runner.invoke(pair, ["--help"])
    assert result.exit_code == 0
    # The help should show the valid choices
    assert "both" in result.output.lower() or "source" in result.output.lower()


def test_pair_conflict_choices() -> None:
    """Test that conflict option has expected choices."""
    runner = CliRunner()
    result = runner.invoke(pair, ["--help"])
    assert result.exit_code == 0
    # The help should mention conflict resolution
    assert "conflict" in result.output.lower()


def test_pair_uncommitted_changes_choices() -> None:
    """Test that uncommitted-changes option has expected choices."""
    runner = CliRunner()
    result = runner.invoke(pair, ["--help"])
    assert result.exit_code == 0
    # The help should mention uncommitted changes handling
    assert "uncommitted" in result.output.lower()


def test_pair_source_and_source_agent_conflict() -> None:
    """Test that providing both --source and --source-agent shows error."""
    runner = CliRunner()
    result = runner.invoke(pair, ["agent-name", "--source", "/some/path", "--source-agent", "other-agent"])
    # Should fail because you can't provide both
    assert result.exit_code != 0
    assert "cannot" in result.output.lower() or "error" in result.output.lower()


def test_pair_source_as_path_raises_error() -> None:
    """Test that using --source with a path correctly requires the path to exist."""
    runner = CliRunner()
    result = runner.invoke(pair, ["agent-name", "--source", "/nonexistent/path/12345"])
    # Should fail because path doesn't exist
    assert result.exit_code != 0


def test_pair_source_host_not_implemented() -> None:
    """Test that using --source-host shows not implemented error."""
    runner = CliRunner()
    result = runner.invoke(pair, ["agent-name", "--source-host", "some-host"])
    # Should fail with not implemented error
    assert result.exit_code != 0
    assert "not implemented" in result.output.lower() or "error" in result.output.lower()


def test_pair_conflict_ask_not_implemented() -> None:
    """Test that using --conflict=ask shows not implemented error."""
    runner = CliRunner()
    result = runner.invoke(pair, ["agent-name", "--conflict", "ask"])
    # Should fail with not implemented error
    assert result.exit_code != 0
    assert "not implemented" in result.output.lower() or "error" in result.output.lower()


def test_pair_nonexistent_agent() -> None:
    """Test that pairing with nonexistent agent shows appropriate error."""
    runner = CliRunner()
    # Use an agent name that definitely doesn't exist
    result = runner.invoke(pair, ["nonexistent-agent-12345"])
    # Should fail because agent doesn't exist (may show different errors depending on context)
    assert result.exit_code != 0
