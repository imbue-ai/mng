from imbue.mng.cli.rename import RenameCliOptions


def test_rename_cli_options_parsing_creates_valid_options() -> None:
    """Test that RenameCliOptions can be constructed with the expected fields."""
    opts = RenameCliOptions(
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
        current="my-agent",
        new_name="new-agent",
        dry_run=False,
        host=False,
    )
    assert opts.current == "my-agent"
    assert opts.new_name == "new-agent"
    assert opts.dry_run is False


def test_rename_cli_options_with_dry_run() -> None:
    """Test RenameCliOptions with dry_run enabled."""
    opts = RenameCliOptions(
        output_format="json",
        quiet=True,
        verbose=1,
        log_file=None,
        log_commands=None,
        log_command_output=None,
        log_env_vars=None,
        project_context_path=None,
        plugin=(),
        disable_plugin=(),
        current="agent-123",
        new_name="renamed-agent",
        dry_run=True,
        host=False,
    )
    assert opts.current == "agent-123"
    assert opts.new_name == "renamed-agent"
    assert opts.dry_run is True
    assert opts.output_format == "json"
    assert opts.quiet is True
