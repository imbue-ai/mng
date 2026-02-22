"""Integration tests for the schedule CLI command."""

import click
import pluggy
from click.testing import CliRunner

from imbue.mng_schedule.cli import schedule


def test_schedule_add_requires_command(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that schedule add requires --command."""
    result = cli_runner.invoke(
        schedule,
        ["add"],
        obj=plugin_manager,
    )
    assert result.exit_code != 0
    assert "--command is required" in result.output


def test_schedule_add_requires_schedule(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that schedule add requires --schedule."""
    result = cli_runner.invoke(
        schedule,
        ["add", "--command", "create"],
        obj=plugin_manager,
    )
    assert result.exit_code != 0
    assert "--schedule is required" in result.output


def test_schedule_add_requires_provider(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that schedule add requires --provider."""
    result = cli_runner.invoke(
        schedule,
        ["add", "--command", "create", "--schedule", "0 2 * * *"],
        obj=plugin_manager,
    )
    assert result.exit_code != 0
    assert "--provider is required" in result.output


def test_schedule_add_rejects_unsupported_provider(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that schedule add rejects unsupported providers."""
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
    assert "not yet supported" in result.output


def test_schedule_add_requires_git_image_hash_for_modal(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that schedule add requires --git-image-hash when provider is modal."""
    result = cli_runner.invoke(
        schedule,
        [
            "add",
            "--command",
            "create",
            "--schedule",
            "0 2 * * *",
            "--provider",
            "modal",
        ],
        obj=plugin_manager,
    )
    assert result.exit_code != 0
    assert "--git-image-hash is required" in result.output


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
    """Test that schedule add accepts name as a positional argument (no UsageError about name)."""
    result = cli_runner.invoke(
        schedule,
        ["add", "my-trigger", "--command", "create"],
        obj=plugin_manager,
    )
    # Should fail due to missing --schedule, not because of positional name
    assert result.exit_code != 0
    assert "Cannot specify both" not in result.output


def test_schedule_update_accepts_positional_name(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that schedule update accepts name as a positional argument (no UsageError)."""
    result = cli_runner.invoke(
        schedule,
        ["update", "my-trigger", "--disabled"],
        obj=plugin_manager,
    )
    assert not isinstance(result.exception, (click.UsageError, SystemExit))


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
    """Test that add and update accept the same trigger options (including --git-image-hash)."""
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
        "--git-image-hash",
        "HEAD",
    ]

    # add will fail trying to resolve git ref in the test env (no git repo)
    # but it should not be a UsageError or click error
    add_result = cli_runner.invoke(
        schedule,
        ["add", *shared_args],
        obj=plugin_manager,
    )
    # Should fail with ScheduleDeployError (wrapped as ClickException), not a UsageError
    assert add_result.exit_code != 0
    assert not isinstance(add_result.exception, click.UsageError)

    update_result = cli_runner.invoke(
        schedule,
        ["update", *shared_args],
        obj=plugin_manager,
    )
    assert isinstance(update_result.exception, NotImplementedError)


def test_schedule_add_accepts_git_image_hash(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that schedule add accepts --git-image-hash option."""
    result = cli_runner.invoke(
        schedule,
        [
            "add",
            "--command",
            "create",
            "--schedule",
            "0 2 * * *",
            "--provider",
            "modal",
            "--git-image-hash",
            "HEAD",
        ],
        obj=plugin_manager,
    )
    # Should get past validation (fails at deploy since no git repo in test env)
    assert result.exit_code != 0
    # Should NOT be a UsageError about missing options
    assert not isinstance(result.exception, click.UsageError)
