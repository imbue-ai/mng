import json

import pluggy
from click.testing import CliRunner

from imbue.mng.api.logs import LogFileEntry
from imbue.mng.cli.conftest import capture_stdout
from imbue.mng.cli.logs import LogsCliOptions
from imbue.mng.cli.logs import _emit_log_content
from imbue.mng.cli.logs import _emit_log_file_list
from imbue.mng.cli.logs import _write_and_flush_stdout
from imbue.mng.cli.logs import logs
from imbue.mng.config.data_types import OutputOptions
from imbue.mng.primitives import OutputFormat


def _make_logs_opts(
    target: str = "my-agent",
    log_filename: str | None = None,
    follow: bool = False,
    tail: int | None = None,
    head: int | None = None,
) -> LogsCliOptions:
    return LogsCliOptions(
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
        target=target,
        log_filename=log_filename,
        follow=follow,
        tail=tail,
        head=head,
    )


def test_logs_cli_options_can_be_constructed() -> None:
    """Verify the options class can be instantiated with all required fields."""
    opts = _make_logs_opts()
    assert opts.target == "my-agent"
    assert opts.follow is False
    assert opts.tail is None
    assert opts.head is None
    assert opts.log_filename is None


def test_logs_cli_options_with_tail() -> None:
    opts = _make_logs_opts(follow=True, tail=50)
    assert opts.follow is True
    assert opts.tail == 50


def test_logs_cli_options_with_head() -> None:
    opts = _make_logs_opts(head=20)
    assert opts.head == 20


def test_logs_cli_rejects_head_and_tail_together(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Verify that --head and --tail cannot be used together."""
    result = cli_runner.invoke(
        logs,
        ["my-agent", "output.log", "--head", "5", "--tail", "10"],
        obj=plugin_manager,
    )
    assert result.exit_code != 0
    assert "Cannot specify both --head and --tail" in result.output


def test_logs_cli_rejects_head_with_follow(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Verify that --head cannot be used with --follow."""
    result = cli_runner.invoke(
        logs,
        ["my-agent", "output.log", "--head", "5", "--follow"],
        obj=plugin_manager,
    )
    assert result.exit_code != 0
    assert "Cannot use --head with --follow" in result.output


def test_logs_nonexistent_agent(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that logs for a non-existent agent returns an error."""
    result = cli_runner.invoke(
        logs,
        ["nonexistent-agent-34892"],
        obj=plugin_manager,
        catch_exceptions=True,
    )

    assert result.exit_code != 0


def test_logs_cli_log_filename_does_not_conflict_with_common_log_file(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Verify the log_filename argument does not collide with the --log-file common option."""
    result = cli_runner.invoke(
        logs,
        ["nonexistent-agent-xyz", "output.log", "--log-file", "/tmp/test-log-82741.log"],
        obj=plugin_manager,
    )
    # Should fail because "nonexistent-agent-xyz" doesn't exist, not because of param conflict
    assert result.exit_code != 0
    assert "nonexistent-agent-xyz" in result.output


# =============================================================================
# Output helper function tests
# =============================================================================


def test_write_and_flush_stdout() -> None:
    """Test _write_and_flush_stdout writes to stdout."""
    with capture_stdout() as buf:
        _write_and_flush_stdout("hello world")
    assert buf.getvalue() == "hello world"


def test_emit_log_file_list_human_empty() -> None:
    """Test _emit_log_file_list with no log files in HUMAN format."""
    output_opts = OutputOptions(output_format=OutputFormat.HUMAN)
    with capture_stdout() as buf:
        _emit_log_file_list([], "my-agent", output_opts)
    assert "No log files found for my-agent" in buf.getvalue()


def test_emit_log_file_list_human_with_files() -> None:
    """Test _emit_log_file_list with log files in HUMAN format."""
    log_files = [
        LogFileEntry(name="output.log", size=1024),
        LogFileEntry(name="error.log", size=512),
    ]
    output_opts = OutputOptions(output_format=OutputFormat.HUMAN)
    with capture_stdout() as buf:
        _emit_log_file_list(log_files, "my-agent", output_opts)
    output = buf.getvalue()
    assert "Log files for my-agent" in output
    assert "output.log" in output
    assert "error.log" in output


def test_emit_log_file_list_json_format() -> None:
    """Test _emit_log_file_list in JSON format."""
    log_files = [
        LogFileEntry(name="output.log", size=1024),
    ]
    output_opts = OutputOptions(output_format=OutputFormat.JSON)
    with capture_stdout() as buf:
        _emit_log_file_list(log_files, "my-agent", output_opts)
    data = json.loads(buf.getvalue().strip())
    assert data["target"] == "my-agent"
    assert len(data["log_files"]) == 1
    assert data["log_files"][0]["name"] == "output.log"


def test_emit_log_file_list_format_template() -> None:
    """Test _emit_log_file_list with a format template."""
    log_files = [
        LogFileEntry(name="output.log", size=1024),
    ]
    output_opts = OutputOptions(output_format=OutputFormat.HUMAN, format_template="{name}")
    with capture_stdout() as buf:
        _emit_log_file_list(log_files, "my-agent", output_opts)
    assert "output.log" in buf.getvalue()


def test_emit_log_content_human_format() -> None:
    """Test _emit_log_content in HUMAN format."""
    output_opts = OutputOptions(output_format=OutputFormat.HUMAN)
    with capture_stdout() as buf:
        _emit_log_content("line 1\nline 2\n", "output.log", output_opts)
    assert "line 1\nline 2\n" in buf.getvalue()


def test_emit_log_content_human_adds_trailing_newline() -> None:
    """Test _emit_log_content adds trailing newline if missing."""
    output_opts = OutputOptions(output_format=OutputFormat.HUMAN)
    with capture_stdout() as buf:
        _emit_log_content("no trailing newline", "output.log", output_opts)
    assert buf.getvalue().endswith("\n")


def test_emit_log_content_json_format() -> None:
    """Test _emit_log_content in JSON format."""
    output_opts = OutputOptions(output_format=OutputFormat.JSON)
    with capture_stdout() as buf:
        _emit_log_content("log content", "output.log", output_opts)
    data = json.loads(buf.getvalue().strip())
    assert data["log_file"] == "output.log"
    assert data["content"] == "log content"


def test_logs_help_exits_zero(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that logs --help works and exits 0."""
    result = cli_runner.invoke(
        logs,
        ["--help"],
        obj=plugin_manager,
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert "logs" in result.output.lower()
