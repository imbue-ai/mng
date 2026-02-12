from imbue.mngr.cli.schedule import ScheduleCliOptions
from imbue.mngr.cli.schedule import _schedule_definition_to_dict
from imbue.mngr.conftest import make_test_schedule_definition


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
    schedule = make_test_schedule_definition()
    result = _schedule_definition_to_dict(schedule, crontab_line="0 * * * * /path/to/mngr create ...")
    assert result["name"] == "test-schedule"
    assert result["message"] == "test message"
    assert result["cron"] == "0 * * * *"
    assert result["template"] == "my-template"
    assert result["crontab_line"] == "0 * * * * /path/to/mngr create ..."
    assert result["is_enabled"] is True


def test_schedule_definition_to_dict_without_crontab_line() -> None:
    schedule = make_test_schedule_definition(template=None)
    result = _schedule_definition_to_dict(schedule, crontab_line=None)
    assert "crontab_line" not in result
    assert result["template"] is None
