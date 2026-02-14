from typing import Any
from typing import assert_never

import click
from loguru import logger

from imbue.imbue_common.pure import pure
from imbue.mngr.api.schedule import ScheduleAddResult
from imbue.mngr.api.schedule import ScheduleDefinition
from imbue.mngr.api.schedule import ScheduleListResult
from imbue.mngr.api.schedule import ScheduleRemoveResult
from imbue.mngr.api.schedule import add_schedule
from imbue.mngr.api.schedule import list_schedules
from imbue.mngr.api.schedule import remove_schedule
from imbue.mngr.api.schedule import run_schedule_now
from imbue.mngr.cli.common_opts import CommonCliOptions
from imbue.mngr.cli.common_opts import add_common_options
from imbue.mngr.cli.common_opts import setup_command_context
from imbue.mngr.cli.help_formatter import CommandHelpMetadata
from imbue.mngr.cli.help_formatter import add_pager_help_option
from imbue.mngr.cli.help_formatter import register_help_metadata
from imbue.mngr.cli.output_helpers import emit_final_json
from imbue.mngr.config.data_types import OutputOptions
from imbue.mngr.primitives import OutputFormat
from imbue.mngr.primitives import ScheduleName


class ScheduleCliOptions(CommonCliOptions):
    """Options for schedule subcommands."""

    name: str | None = None
    message: str | None = None
    template: str | None = None
    cron: str | None = None
    create_args: tuple[str, ...] = ()


@click.group(name="schedule", invoke_without_command=True)
@add_common_options
@click.pass_context
def schedule(ctx: click.Context, **kwargs: Any) -> None:
    """Manage scheduled agents.

    Create, list, and remove cron-based schedules that periodically
    run 'mngr create' to spin up agents.

    Examples:

      mngr schedule add --cron "0 * * * *" --template my-hook "fix flaky tests" --name hourly-fixer

      mngr schedule list

      mngr schedule remove hourly-fixer

      mngr schedule run hourly-fixer
    """
    if ctx.invoked_subcommand is None:
        logger.info(ctx.get_help())


@schedule.command(name="add")
@click.argument("message")
@click.option("--name", required=True, help="Name for this schedule (must be unique)")
@click.option("--cron", required=True, help="Cron expression (e.g. '0 * * * *' for hourly)")
@click.option("--template", default=None, help="Create template to use")
@click.argument("create_args", nargs=-1, type=click.UNPROCESSED)
@add_common_options
@click.pass_context
def schedule_add(ctx: click.Context, message: str, create_args: tuple[str, ...], **kwargs: Any) -> None:
    """Add a new scheduled agent.

    MESSAGE is the initial message to send to the created agent.

    Any additional arguments after the message are passed through to 'mngr create'.

    Examples:

      mngr schedule add --cron "0 * * * *" --template my-hook "fix flaky tests" --name hourly-fixer

      mngr schedule add --cron "0 9 * * 1-5" "review open PRs" --name daily-reviewer
    """
    mngr_ctx, output_opts, opts = setup_command_context(
        ctx=ctx,
        command_name="schedule",
        command_class=ScheduleCliOptions,
    )

    assert opts.name is not None
    assert opts.cron is not None

    result = add_schedule(
        name=ScheduleName(opts.name),
        message=message,
        cron=opts.cron,
        template=opts.template,
        create_args=create_args,
        mngr_ctx=mngr_ctx,
    )

    _emit_schedule_add_result(result, output_opts)


def _emit_schedule_add_result(result: ScheduleAddResult, output_opts: OutputOptions) -> None:
    match output_opts.output_format:
        case OutputFormat.JSON:
            emit_final_json(_schedule_definition_to_dict(result.schedule, result.crontab_line))
        case OutputFormat.JSONL:
            emit_final_json(
                {"event": "schedule_added", **_schedule_definition_to_dict(result.schedule, result.crontab_line)}
            )
        case OutputFormat.HUMAN:
            logger.info("Added schedule '{}' with cron '{}'", result.schedule.name, result.schedule.cron)
            logger.info("Crontab entry: {}", result.crontab_line)
        case _ as unreachable:
            assert_never(unreachable)


@schedule.command(name="list")
@add_common_options
@click.pass_context
def schedule_list(ctx: click.Context, **kwargs: Any) -> None:
    """List all schedules.

    Examples:

      mngr schedule list

      mngr schedule list --format json
    """
    mngr_ctx, output_opts, _opts = setup_command_context(
        ctx=ctx,
        command_name="schedule",
        command_class=ScheduleCliOptions,
    )

    result = list_schedules(mngr_ctx=mngr_ctx)
    _emit_schedule_list_result(result, output_opts)


def _emit_schedule_list_result(result: ScheduleListResult, output_opts: OutputOptions) -> None:
    match output_opts.output_format:
        case OutputFormat.JSON:
            emit_final_json(
                {"schedules": [_schedule_definition_to_dict(s, crontab_line=None) for s in result.schedules]}
            )
        case OutputFormat.JSONL:
            for s in result.schedules:
                emit_final_json({"event": "schedule", **_schedule_definition_to_dict(s, crontab_line=None)})
        case OutputFormat.HUMAN:
            if not result.schedules:
                logger.info("No schedules configured.")
            else:
                for s in result.schedules:
                    enabled_str = "enabled" if s.is_enabled else "disabled"
                    template_str = f" (template: {s.template})" if s.template else ""
                    logger.info(
                        "  {} [{}] cron='{}'{} -- {}",
                        s.name,
                        enabled_str,
                        s.cron,
                        template_str,
                        s.message,
                    )
        case _ as unreachable:
            assert_never(unreachable)


@schedule.command(name="remove")
@click.argument("name")
@add_common_options
@click.pass_context
def schedule_remove(ctx: click.Context, name: str, **kwargs: Any) -> None:
    """Remove a schedule.

    NAME is the name of the schedule to remove.

    Examples:

      mngr schedule remove hourly-fixer
    """
    mngr_ctx, output_opts, _opts = setup_command_context(
        ctx=ctx,
        command_name="schedule",
        command_class=ScheduleCliOptions,
    )

    result = remove_schedule(
        name=ScheduleName(name),
        mngr_ctx=mngr_ctx,
    )
    _emit_schedule_remove_result(result, output_opts)


def _emit_schedule_remove_result(result: ScheduleRemoveResult, output_opts: OutputOptions) -> None:
    match output_opts.output_format:
        case OutputFormat.JSON:
            emit_final_json({"name": str(result.name), "removed": True})
        case OutputFormat.JSONL:
            emit_final_json({"event": "schedule_removed", "name": str(result.name)})
        case OutputFormat.HUMAN:
            logger.info("Removed schedule '{}'", result.name)
        case _ as unreachable:
            assert_never(unreachable)


@schedule.command(name="run")
@click.argument("name")
@add_common_options
@click.pass_context
def schedule_run(ctx: click.Context, name: str, **kwargs: Any) -> None:
    """Run a schedule immediately.

    NAME is the name of the schedule to run. This executes the schedule's
    'mngr create' command directly without waiting for the next cron trigger.

    Examples:

      mngr schedule run hourly-fixer
    """
    mngr_ctx, output_opts, _opts = setup_command_context(
        ctx=ctx,
        command_name="schedule",
        command_class=ScheduleCliOptions,
    )

    run_schedule_now(
        name=ScheduleName(name),
        mngr_ctx=mngr_ctx,
    )

    match output_opts.output_format:
        case OutputFormat.JSON:
            emit_final_json({"name": name, "executed": True})
        case OutputFormat.JSONL:
            emit_final_json({"event": "schedule_executed", "name": name})
        case OutputFormat.HUMAN:
            logger.info("Executed schedule '{}'", name)
        case _ as unreachable:
            assert_never(unreachable)


@pure
def _schedule_definition_to_dict(
    schedule: ScheduleDefinition,
    crontab_line: str | None,
) -> dict[str, Any]:
    """Convert a ScheduleDefinition to a JSON-serializable dict."""
    result: dict[str, Any] = {
        "name": str(schedule.name),
        "message": schedule.message,
        "cron": schedule.cron,
        "template": schedule.template,
        "create_args": list(schedule.create_args),
        "created_at": schedule.created_at.isoformat(),
        "is_enabled": schedule.is_enabled,
    }
    if crontab_line is not None:
        result["crontab_line"] = crontab_line
    return result


_SCHEDULE_HELP_METADATA = CommandHelpMetadata(
    name="mngr-schedule",
    one_line_description="Manage scheduled agents",
    synopsis="mngr schedule <subcommand> [OPTIONS]",
    description="""Manage cron-based schedules that periodically run 'mngr create' to spin up agents.

Schedules are stored in ~/.mngr/profiles/<id>/schedules.toml and executed
via the system crontab. Each schedule installs a crontab entry that runs
'mngr create' with the specified arguments.

Output from scheduled runs is logged to $HOME/.mngr/logs/schedule-<name>.log.""",
    examples=(
        (
            "Add an hourly schedule using a template",
            'mngr schedule add --cron "0 * * * *" --template my-hook "fix flaky tests" --name hourly-fixer',
        ),
        (
            "Add a weekday morning schedule",
            'mngr schedule add --cron "0 9 * * 1-5" "review open PRs" --name pr-reviewer',
        ),
        ("List all schedules", "mngr schedule list"),
        ("List schedules in JSON format", "mngr schedule list --format json"),
        ("Remove a schedule", "mngr schedule remove hourly-fixer"),
        ("Run a schedule immediately", "mngr schedule run hourly-fixer"),
    ),
    see_also=(
        ("create", "Create a new agent"),
        ("config", "Configure create templates used by schedules"),
    ),
)

register_help_metadata("schedule", _SCHEDULE_HELP_METADATA)

add_pager_help_option(schedule)
