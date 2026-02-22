"""Unit tests for the schedule CLI command."""

import pytest
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


@pytest.mark.parametrize(
    ("subcommand", "expected_options"),
    [
        ("add", ["--name", "--command", "--args", "--schedule", "--provider", "--update"]),
        ("remove", ["--force"]),
        ("update", ["--command", "--args", "--schedule", "--provider"]),
        ("list", ["--all"]),
        ("run", ["--local"]),
    ],
)
def test_subcommand_help_shows_options(subcommand: str, expected_options: list[str]) -> None:
    """Test that each subcommand's --help shows its expected options."""
    runner = CliRunner()
    result = runner.invoke(schedule, [subcommand, "--help"])
    assert result.exit_code == 0
    for option in expected_options:
        assert option in result.output


@pytest.mark.parametrize(
    ("options_class", "expected_fields"),
    [
        (ScheduleAddCliOptions, ["name", "command", "args", "schedule_cron", "provider", "update", "enabled"]),
        (ScheduleRemoveCliOptions, ["names", "force"]),
        (ScheduleUpdateCliOptions, ["name", "command", "args", "schedule_cron", "provider", "enabled"]),
        (ScheduleListCliOptions, ["all_schedules"]),
        (ScheduleRunCliOptions, ["name", "local"]),
    ],
)
def test_cli_options_has_all_fields(options_class: type, expected_fields: list[str]) -> None:
    """Test that each CLI options class has all required fields."""
    annotations = options_class.__annotations__
    for field in expected_fields:
        assert field in annotations
