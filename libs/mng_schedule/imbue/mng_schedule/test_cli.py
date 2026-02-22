"""Integration tests for the schedule CLI command."""

import pluggy
from click.testing import CliRunner

from imbue.mng_schedule.cli import schedule


def test_schedule_add_raises_not_implemented(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that schedule add raises NotImplementedError (not a different error)."""
    result = cli_runner.invoke(
        schedule,
        [
            "add",
            "--command",
            "create",
            "--schedule",
            "0 2 * * *",
            "--provider",
            "local",
        ],
        obj=plugin_manager,
    )
    assert result.exit_code != 0
    assert result.exception is not None
    assert isinstance(result.exception, NotImplementedError)
    assert "schedule add is not implemented yet" in str(result.exception)


def test_schedule_add_with_no_options_raises_not_implemented(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that schedule add with no options reaches the handler (all options are optional at click level)."""
    result = cli_runner.invoke(
        schedule,
        ["add"],
        obj=plugin_manager,
    )
    assert result.exit_code != 0
    assert result.exception is not None
    assert isinstance(result.exception, NotImplementedError)
    assert "schedule add is not implemented yet" in str(result.exception)


def test_schedule_update_raises_not_implemented(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that schedule update raises NotImplementedError with shared options."""
    result = cli_runner.invoke(
        schedule,
        [
            "update",
            "--name",
            "my-trigger",
            "--disabled",
        ],
        obj=plugin_manager,
    )
    assert result.exit_code != 0
    assert result.exception is not None
    assert isinstance(result.exception, NotImplementedError)
    assert "schedule update is not implemented yet" in str(result.exception)


def test_schedule_add_accepts_positional_name(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that schedule add accepts name as a positional argument."""
    result = cli_runner.invoke(
        schedule,
        ["add", "my-trigger", "--command", "create"],
        obj=plugin_manager,
    )
    assert isinstance(result.exception, NotImplementedError)


def test_schedule_update_accepts_positional_name(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that schedule update accepts name as a positional argument."""
    result = cli_runner.invoke(
        schedule,
        ["update", "my-trigger", "--disabled"],
        obj=plugin_manager,
    )
    assert isinstance(result.exception, NotImplementedError)


def test_schedule_add_rejects_both_positional_and_option_name(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that specifying both positional name and --name is an error."""
    result = cli_runner.invoke(
        schedule,
        ["add", "pos-name", "--name", "opt-name"],
        obj=plugin_manager,
    )
    assert result.exit_code != 0
    assert "Cannot specify both" in result.output


def test_schedule_add_and_update_share_options(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that add and update accept the same trigger options."""
    shared_args = [
        "--name",
        "test-trigger",
        "--command",
        "create",
        "--schedule",
        "0 3 * * *",
        "--provider",
        "modal",
        "--no-verify",
    ]

    add_result = cli_runner.invoke(
        schedule,
        ["add", *shared_args],
        obj=plugin_manager,
    )
    assert isinstance(add_result.exception, NotImplementedError)

    update_result = cli_runner.invoke(
        schedule,
        ["update", *shared_args],
        obj=plugin_manager,
    )
    assert isinstance(update_result.exception, NotImplementedError)


def test_schedule_add_with_full_verify(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that schedule add accepts --full-verify."""
    result = cli_runner.invoke(
        schedule,
        [
            "add",
            "--command",
            "create",
            "--schedule",
            "0 2 * * *",
            "--provider",
            "local",
            "--full-verify",
        ],
        obj=plugin_manager,
    )
    assert result.exit_code != 0
    assert isinstance(result.exception, NotImplementedError)
    assert "schedule add is not implemented yet" in str(result.exception)
