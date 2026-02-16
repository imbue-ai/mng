from imbue.mngr.cli.logs import LogsCliOptions


def test_logs_cli_options_can_be_constructed() -> None:
    """Verify the options class can be instantiated with all required fields."""
    opts = LogsCliOptions(
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
        target="my-agent",
        follow=False,
        tail=None,
        head=None,
    )
    assert opts.target == "my-agent"
    assert opts.follow is False
    assert opts.tail is None
    assert opts.head is None
    assert opts.log_file is None


def test_logs_cli_options_with_tail() -> None:
    opts = LogsCliOptions(
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
        target="my-agent",
        follow=True,
        tail=50,
        head=None,
    )
    assert opts.follow is True
    assert opts.tail == 50


def test_logs_cli_options_with_head() -> None:
    opts = LogsCliOptions(
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
        target="my-agent",
        follow=False,
        tail=None,
        head=20,
    )
    assert opts.head == 20
