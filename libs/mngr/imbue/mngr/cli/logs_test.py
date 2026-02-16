import pluggy
from click.testing import CliRunner

from imbue.mngr.cli.logs import LogsCliOptions
from imbue.mngr.cli.logs import logs


def _make_logs_opts(
    target: str = "my-agent",
    log_filename: str | None = None,
    follow: bool = False,
    tail: int | None = None,
    head: int | None = None,
    allow_unknown_host: bool = False,
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
        allow_unknown_host=allow_unknown_host,
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
