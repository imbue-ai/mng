"""Unit tests for the push CLI command."""

import pluggy
from click.testing import CliRunner

from imbue.mng.cli.push import PushCliOptions
from imbue.mng.cli.push import push


def test_push_cli_options_can_be_instantiated() -> None:
    """Test that PushCliOptions can be instantiated with all required fields."""
    opts = PushCliOptions(
        target_pos=None,
        source_pos=None,
        target=None,
        target_agent=None,
        target_host=None,
        target_path=None,
        source=None,
        dry_run=False,
        stop=False,
        delete=False,
        sync_mode="files",
        exclude=(),
        uncommitted_changes="fail",
        source_branch=None,
        mirror=False,
        rsync_only=False,
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
    assert opts.sync_mode == "files"
    assert opts.dry_run is False
    assert opts.delete is False
    assert opts.uncommitted_changes == "fail"


def test_push_nonexistent_agent(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test pushing to a non-existent agent returns error."""
    result = cli_runner.invoke(
        push,
        ["nonexistent-agent-77312"],
        obj=plugin_manager,
        catch_exceptions=True,
    )

    assert result.exit_code != 0
