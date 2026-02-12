import shlex
from pathlib import Path

import pytest
from pydantic import ValidationError

from imbue.mngr.api.schedule import _build_crontab_command
from imbue.mngr.api.schedule import _crontab_marker
from imbue.mngr.api.schedule import _load_schedules
from imbue.mngr.api.schedule import _save_schedules
from imbue.mngr.conftest import make_test_schedule_definition
from imbue.mngr.primitives import ScheduleName


def test_crontab_marker_contains_schedule_name() -> None:
    name = ScheduleName("my-schedule")
    marker = _crontab_marker(name)
    assert marker == "# mngr-schedule:my-schedule"


def test_crontab_marker_for_prefix_name_is_not_substring_of_longer_name() -> None:
    """Verify that marker for 'foo' does not match as a suffix of 'foobar' marker."""
    short_marker = _crontab_marker(ScheduleName("foo"))
    long_marker = _crontab_marker(ScheduleName("foobar"))

    # The short marker should NOT be a suffix of a line ending with the long marker
    sample_line = f"0 * * * * /usr/bin/mngr create --message test {long_marker}"
    assert not sample_line.rstrip().endswith(short_marker)


def test_build_crontab_command_with_template() -> None:
    schedule = make_test_schedule_definition(
        name="hourly-fixer",
        template="my-hook",
        message="fix flaky tests",
        cron="0 * * * *",
    )
    line = _build_crontab_command(schedule, "/usr/local/bin/mngr")
    assert line.startswith("0 * * * * /usr/local/bin/mngr create")
    assert "--template my-hook" in line
    assert "--no-connect" in line
    assert shlex.quote("fix flaky tests") in line
    assert "# mngr-schedule:hourly-fixer" in line
    assert "schedule-hourly-fixer.log" in line


def test_build_crontab_command_without_template() -> None:
    schedule = make_test_schedule_definition(
        name="no-tpl",
        template=None,
        message="run something",
        cron="*/5 * * * *",
    )
    line = _build_crontab_command(schedule, "/path/to/mngr")
    assert "--template" not in line
    assert shlex.quote("run something") in line


def test_build_crontab_command_with_create_args() -> None:
    schedule = make_test_schedule_definition(
        name="with-args",
        create_args=("--in", "modal", "--idle-timeout", "120"),
    )
    line = _build_crontab_command(schedule, "/usr/local/bin/mngr")
    assert "--in modal --idle-timeout 120" in line


def test_save_and_load_schedules_roundtrip(tmp_path: Path) -> None:
    schedules_path = tmp_path / "schedules.toml"
    schedules = [
        make_test_schedule_definition(name="schedule-a", template="tpl-a", message="msg a"),
        make_test_schedule_definition(name="schedule-b", template=None, message="msg b", cron="*/10 * * * *"),
    ]

    _save_schedules(schedules_path, schedules)

    loaded = _load_schedules(schedules_path)
    assert len(loaded) == 2
    assert loaded[0].name == ScheduleName("schedule-a")
    assert loaded[0].template == "tpl-a"
    assert loaded[0].message == "msg a"
    assert loaded[0].cron == "0 * * * *"
    assert loaded[0].is_enabled is True
    assert loaded[1].name == ScheduleName("schedule-b")
    assert loaded[1].template is None
    assert loaded[1].cron == "*/10 * * * *"


def test_load_schedules_returns_empty_for_missing_file(tmp_path: Path) -> None:
    path = tmp_path / "nonexistent.toml"
    assert _load_schedules(path) == []


def test_save_schedules_creates_parent_directories(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "dir" / "schedules.toml"
    _save_schedules(path, [make_test_schedule_definition()])
    assert path.exists()
    loaded = _load_schedules(path)
    assert len(loaded) == 1


def test_save_and_load_with_create_args(tmp_path: Path) -> None:
    schedules_path = tmp_path / "schedules.toml"
    schedule = make_test_schedule_definition(
        name="with-extra-args",
        create_args=("--in", "modal", "--idle-timeout", "60"),
    )
    _save_schedules(schedules_path, [schedule])

    loaded = _load_schedules(schedules_path)
    assert loaded[0].create_args == ("--in", "modal", "--idle-timeout", "60")


def test_build_crontab_command_quotes_values_with_spaces() -> None:
    schedule = make_test_schedule_definition(
        name="space-test",
        template="my template",
        message="fix the tests",
    )
    line = _build_crontab_command(schedule, "/path with spaces/mngr")
    assert shlex.quote("/path with spaces/mngr") in line
    assert shlex.quote("my template") in line
    assert shlex.quote("fix the tests") in line


def test_build_crontab_command_quotes_create_args_with_spaces() -> None:
    schedule = make_test_schedule_definition(
        name="args-test",
        create_args=("--label", "my label value"),
    )
    line = _build_crontab_command(schedule, "/usr/local/bin/mngr")
    assert shlex.quote("my label value") in line


def test_build_crontab_command_uses_home_env_var_for_log_path() -> None:
    schedule = make_test_schedule_definition(name="test-log-path")
    line = _build_crontab_command(schedule, "/usr/local/bin/mngr")
    assert "$HOME/.mngr/logs/" in line
    assert "~/" not in line


def test_build_crontab_command_quotes_log_filename_with_spaces() -> None:
    schedule = make_test_schedule_definition(name="name with spaces")
    line = _build_crontab_command(schedule, "/usr/local/bin/mngr")
    # The log filename should be quoted to prevent shell injection
    assert shlex.quote("schedule-name with spaces.log") in line


def test_schedule_definition_is_frozen() -> None:
    schedule = make_test_schedule_definition()
    with pytest.raises(ValidationError):
        schedule.name = ScheduleName("changed")
