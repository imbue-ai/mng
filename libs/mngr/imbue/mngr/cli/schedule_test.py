from datetime import datetime
from datetime import timezone

from imbue.mngr.api.schedule import ScheduleDefinition
from imbue.mngr.cli.schedule import ScheduleCliOptions
from imbue.mngr.cli.schedule import _schedule_definition_to_dict
from imbue.mngr.primitives import ScheduleName


def _make_schedule_def(
    name: str = "test-sched",
    template: str | None = "my-tpl",
    message: str = "do something",
) -> ScheduleDefinition:
    return ScheduleDefinition(
        name=ScheduleName(name),
        template=template,
        message=message,
        cron="0 * * * *",
        create_args=(),
        created_at=datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
        is_enabled=True,
    )


def test_schedule_cli_options_defaults() -> None:
    opts = ScheduleCliOptions(
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
    assert opts.name is None
    assert opts.message is None
    assert opts.template is None
    assert opts.cron is None
    assert opts.create_args == ()


def test_schedule_definition_to_dict_with_crontab_line() -> None:
    schedule = _make_schedule_def()
    result = _schedule_definition_to_dict(schedule, crontab_line="0 * * * * /path/to/mngr create ...")
    assert result["name"] == "test-sched"
    assert result["message"] == "do something"
    assert result["cron"] == "0 * * * *"
    assert result["template"] == "my-tpl"
    assert result["crontab_line"] == "0 * * * * /path/to/mngr create ..."
    assert result["is_enabled"] is True


def test_schedule_definition_to_dict_without_crontab_line() -> None:
    schedule = _make_schedule_def(template=None)
    result = _schedule_definition_to_dict(schedule)
    assert "crontab_line" not in result
    assert result["template"] is None
