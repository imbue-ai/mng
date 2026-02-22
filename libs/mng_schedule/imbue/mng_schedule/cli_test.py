"""Unit tests for the schedule CLI command."""

from click.testing import CliRunner

from imbue.mng_schedule.cli import ScheduleAddCliOptions
from imbue.mng_schedule.cli import ScheduleListCliOptions
from imbue.mng_schedule.cli import ScheduleRemoveCliOptions
from imbue.mng_schedule.cli import ScheduleRunCliOptions
from imbue.mng_schedule.cli import ScheduleUpdateCliOptions
from imbue.mng_schedule.cli import schedule


def test_schedule_command_is_registered() -> None:
    """Test that the schedule command group is properly registered."""
    assert schedule is not None
    assert schedule.name == "schedule"


def test_schedule_command_has_subcommands() -> None:
    """Test that all expected subcommands are registered."""
    subcommand_names = list(schedule.commands.keys())
    assert "add" in subcommand_names
    assert "remove" in subcommand_names
    assert "update" in subcommand_names
    assert "list" in subcommand_names
    assert "run" in subcommand_names


def test_schedule_add_help_shows_options() -> None:
    """Test that 'schedule add --help' shows all expected options."""
    runner = CliRunner()
    result = runner.invoke(schedule, ["add", "--help"])
    assert result.exit_code == 0
    assert "--name" in result.output
    assert "--command" in result.output
    assert "--args" in result.output
    assert "--schedule" in result.output
    assert "--provider" in result.output
    assert "--update" in result.output
    assert "--enabled" in result.output or "--disabled" in result.output


def test_schedule_remove_help_shows_options() -> None:
    """Test that 'schedule remove --help' shows expected options."""
    runner = CliRunner()
    result = runner.invoke(schedule, ["remove", "--help"])
    assert result.exit_code == 0
    assert "--force" in result.output


def test_schedule_update_help_shows_options() -> None:
    """Test that 'schedule update --help' shows expected options."""
    runner = CliRunner()
    result = runner.invoke(schedule, ["update", "--help"])
    assert result.exit_code == 0
    assert "--command" in result.output
    assert "--args" in result.output
    assert "--schedule" in result.output
    assert "--provider" in result.output
    assert "--enabled" in result.output or "--disabled" in result.output


def test_schedule_list_help_shows_options() -> None:
    """Test that 'schedule list --help' shows expected options."""
    runner = CliRunner()
    result = runner.invoke(schedule, ["list", "--help"])
    assert result.exit_code == 0
    assert "--all" in result.output


def test_schedule_run_help_shows_options() -> None:
    """Test that 'schedule run --help' shows expected options."""
    runner = CliRunner()
    result = runner.invoke(schedule, ["run", "--help"])
    assert result.exit_code == 0
    assert "--local" in result.output


def test_schedule_add_cli_options_has_all_fields() -> None:
    """Test that ScheduleAddCliOptions has all required fields."""
    annotations = ScheduleAddCliOptions.__annotations__
    assert "name" in annotations
    assert "command" in annotations
    assert "args" in annotations
    assert "schedule_cron" in annotations
    assert "provider" in annotations
    assert "update" in annotations
    assert "enabled" in annotations


def test_schedule_remove_cli_options_has_all_fields() -> None:
    """Test that ScheduleRemoveCliOptions has all required fields."""
    annotations = ScheduleRemoveCliOptions.__annotations__
    assert "names" in annotations
    assert "force" in annotations


def test_schedule_update_cli_options_has_all_fields() -> None:
    """Test that ScheduleUpdateCliOptions has all required fields."""
    annotations = ScheduleUpdateCliOptions.__annotations__
    assert "name" in annotations
    assert "command" in annotations
    assert "schedule_cron" in annotations
    assert "provider" in annotations
    assert "enabled" in annotations


def test_schedule_list_cli_options_has_all_fields() -> None:
    """Test that ScheduleListCliOptions has all required fields."""
    annotations = ScheduleListCliOptions.__annotations__
    assert "all_schedules" in annotations


def test_schedule_run_cli_options_has_all_fields() -> None:
    """Test that ScheduleRunCliOptions has all required fields."""
    annotations = ScheduleRunCliOptions.__annotations__
    assert "name" in annotations
    assert "local" in annotations
