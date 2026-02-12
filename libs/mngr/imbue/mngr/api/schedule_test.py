from datetime import datetime
from datetime import timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from imbue.mngr.api.schedule import ScheduleDefinition
from imbue.mngr.api.schedule import _build_crontab_command
from imbue.mngr.api.schedule import _crontab_marker
from imbue.mngr.api.schedule import _load_schedules
from imbue.mngr.api.schedule import _save_schedules
from imbue.mngr.api.schedule import _shell_quote
from imbue.mngr.primitives import ScheduleName


def _make_schedule(
    name: str = "test-schedule",
    template: str | None = "my-template",
    message: str = "test message",
    cron: str = "0 * * * *",
    create_args: tuple[str, ...] = (),
) -> ScheduleDefinition:
    return ScheduleDefinition(
        name=ScheduleName(name),
        template=template,
        message=message,
        cron=cron,
        create_args=create_args,
        created_at=datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
        is_enabled=True,
    )


def test_crontab_marker_contains_schedule_name() -> None:
    name = ScheduleName("my-schedule")
    marker = _crontab_marker(name)
    assert marker == "# mngr-schedule:my-schedule"


def test_shell_quote_simple_string() -> None:
    assert _shell_quote("hello world") == "'hello world'"


def test_shell_quote_string_with_single_quotes() -> None:
    assert _shell_quote("it's a test") == "'it'\\''s a test'"


def test_build_crontab_command_with_template() -> None:
    schedule = _make_schedule(
        name="hourly-fixer",
        template="my-hook",
        message="fix flaky tests",
        cron="0 * * * *",
    )
    line = _build_crontab_command(schedule, "/usr/local/bin/mngr")
    assert line.startswith("0 * * * * /usr/local/bin/mngr create")
    assert "--template my-hook" in line
    assert "--no-connect" in line
    assert "'fix flaky tests'" in line
    assert "# mngr-schedule:hourly-fixer" in line
    assert "schedule-hourly-fixer.log" in line


def test_build_crontab_command_without_template() -> None:
    schedule = _make_schedule(
        name="no-tpl",
        template=None,
        message="run something",
        cron="*/5 * * * *",
    )
    line = _build_crontab_command(schedule, "/path/to/mngr")
    assert "--template" not in line
    assert "'run something'" in line


def test_build_crontab_command_with_create_args() -> None:
    schedule = _make_schedule(
        name="with-args",
        create_args=("--in", "modal", "--idle-timeout", "120"),
    )
    line = _build_crontab_command(schedule, "/usr/local/bin/mngr")
    assert "--in modal --idle-timeout 120" in line


def test_save_and_load_schedules_roundtrip(tmp_path: Path) -> None:
    schedules_path = tmp_path / "schedules.toml"
    schedules = [
        _make_schedule(name="schedule-a", template="tpl-a", message="msg a"),
        _make_schedule(name="schedule-b", template=None, message="msg b", cron="*/10 * * * *"),
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
    _save_schedules(path, [_make_schedule()])
    assert path.exists()
    loaded = _load_schedules(path)
    assert len(loaded) == 1


def test_save_and_load_with_create_args(tmp_path: Path) -> None:
    schedules_path = tmp_path / "schedules.toml"
    schedule = _make_schedule(
        name="with-extra-args",
        create_args=("--in", "modal", "--idle-timeout", "60"),
    )
    _save_schedules(schedules_path, [schedule])

    loaded = _load_schedules(schedules_path)
    assert loaded[0].create_args == ("--in", "modal", "--idle-timeout", "60")


def test_schedule_definition_is_frozen() -> None:
    schedule = _make_schedule()
    with pytest.raises(ValidationError):
        schedule.name = ScheduleName("changed")
