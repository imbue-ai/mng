from typing import Any

import click
from click_option_group import optgroup

from imbue.mng.cli.common_opts import CommonCliOptions
from imbue.mng.cli.common_opts import add_common_options
from imbue.mng.cli.common_opts import setup_command_context
from imbue.mng.cli.default_command_group import DefaultCommandGroup
from imbue.mng.cli.help_formatter import CommandHelpMetadata
from imbue.mng.cli.help_formatter import add_pager_help_option
from imbue.mng.cli.help_formatter import register_help_metadata

# =============================================================================
# CLI Options
# =============================================================================


class ScheduleUpdateCliOptions(CommonCliOptions):
    """Options for the schedule update subcommand."""

    name: str
    command: str | None
    args: str | None
    schedule_cron: str | None
    provider: str | None
    enabled: bool | None


class ScheduleAddCliOptions(ScheduleUpdateCliOptions):
    """
    Options for the schedule add subcommand.

    These are exactly the same as update--the only difference is whether we error if the name already exists.
    """

    update: bool


class ScheduleRemoveCliOptions(CommonCliOptions):
    """Options for the schedule remove subcommand."""

    names: tuple[str, ...]
    force: bool


class ScheduleListCliOptions(CommonCliOptions):
    """Options for the schedule list subcommand."""

    all_schedules: bool


class ScheduleRunCliOptions(CommonCliOptions):
    """Options for the schedule run subcommand."""

    name: str
    local: bool


# =============================================================================
# CLI Group
# =============================================================================


class _ScheduleGroup(DefaultCommandGroup):
    """Schedule group that defaults to 'list' when no subcommand is given."""

    _default_command = "list"
    _config_key = "schedule"


@click.group(name="schedule", cls=_ScheduleGroup)
@add_common_options
@click.pass_context
def schedule(ctx: click.Context, **kwargs: Any) -> None:
    """Schedule remote invocations of mng commands.

    Manage cron-scheduled triggers that run mng commands (create, start,
    message, exec) on a specified provider at regular intervals.

    \b
    Examples:
      mng schedule add my-trigger --command create --args '--message "Create a PR that just says hello" --in modal' --schedule "0 2 * * *" --provider modal
      mng schedule list
      mng schedule remove my-trigger
      mng schedule run my-trigger
    """


# =============================================================================
# add subcommand
# =============================================================================


@schedule.command(name="add")
@optgroup.group("Trigger Definition")
@optgroup.option(
    "--name",
    default=None,
    help="Name for this scheduled trigger. If not specified, a random name is generated.",
)
@optgroup.option(
    "--command",
    "command",
    required=True,
    type=click.Choice(["create", "start", "message", "exec"], case_sensitive=False),
    help="Which mng command to run when triggered.",
)
@optgroup.option(
    "--args",
    "args",
    default=None,
    help="Arguments to pass to the mng command (as a string).",
)
@optgroup.option(
    "--schedule",
    "schedule_cron",
    required=True,
    help="Cron schedule expression defining when the command runs (e.g. '0 2 * * *').",
)
@optgroup.group("Execution")
@optgroup.option(
    "--provider",
    required=True,
    help="Provider in which to schedule the call (e.g. 'local', 'modal').",
)
@optgroup.group("Behavior")
@optgroup.option(
    "--update",
    is_flag=True,
    help="If a schedule with the same name already exists, update it instead of failing.",
)
@optgroup.option(
    "--enabled/--disabled",
    "enabled",
    default=True,
    show_default=True,
    help="Whether the schedule is enabled. Use --disabled to create without activating.",
)
@add_common_options
@click.pass_context
def schedule_add(ctx: click.Context, **kwargs: Any) -> None:
    """Add a new scheduled trigger.

    Creates a new cron-scheduled trigger that will run the specified mng
    command at the specified interval on the specified provider.

    \b
    Examples:
      mng schedule add --command create --args "--type claude --message 'fix bugs' --in modal" --schedule "0 2 * * *" --provider modal
    """
    _mng_ctx, _output_opts, _opts = setup_command_context(
        ctx=ctx,
        command_name="schedule_add",
        command_class=ScheduleAddCliOptions,
    )
    raise NotImplementedError("schedule add is not implemented yet")


# =============================================================================
# remove subcommand
# =============================================================================


@schedule.command(name="remove")
@click.argument("names", nargs=-1, required=True)
@optgroup.group("Safety")
@optgroup.option(
    "-f",
    "--force",
    is_flag=True,
    help="Skip confirmation prompt.",
)
@add_common_options
@click.pass_context
def schedule_remove(ctx: click.Context, **kwargs: Any) -> None:
    """Remove one or more scheduled triggers.

    \b
    Examples:
      mng schedule remove my-trigger
      mng schedule remove trigger-1 trigger-2 --force
    """
    _mng_ctx, _output_opts, _opts = setup_command_context(
        ctx=ctx,
        command_name="schedule_remove",
        command_class=ScheduleRemoveCliOptions,
    )
    raise NotImplementedError("schedule remove is not implemented yet")


# =============================================================================
# update subcommand
# =============================================================================


@schedule.command(name="update")
@click.argument("name", required=True)
@optgroup.group("Trigger Definition")
@optgroup.option(
    "--command",
    "command",
    type=click.Choice(["create", "start", "message", "exec"], case_sensitive=False),
    default=None,
    help="Which mng command to run when triggered.",
)
@optgroup.option(
    "--args",
    "args",
    default=None,
    help="Arguments to pass to the mng command (as a string).",
)
@optgroup.option(
    "--schedule",
    "schedule_cron",
    default=None,
    help="Cron schedule expression defining when the command runs.",
)
@optgroup.group("Execution")
@optgroup.option(
    "--provider",
    default=None,
    help="Provider in which to schedule the call.",
)
@optgroup.group("Behavior")
@optgroup.option(
    "--enabled/--disabled",
    "enabled",
    default=None,
    help="Whether the schedule is enabled.",
)
@add_common_options
@click.pass_context
def schedule_update(ctx: click.Context, **kwargs: Any) -> None:
    """Update an existing scheduled trigger.

    The args are exactly the same as the add command.
    """
    _mng_ctx, _output_opts, _opts = setup_command_context(
        ctx=ctx,
        command_name="schedule_update",
        command_class=ScheduleUpdateCliOptions,
    )
    raise NotImplementedError("schedule update is not implemented yet")


# =============================================================================
# list subcommand
# =============================================================================


@schedule.command(name="list")
@optgroup.group("Filtering")
@optgroup.option(
    "-a",
    "--all",
    "all_schedules",
    is_flag=True,
    help="Show all schedules, including disabled ones.",
)
@add_common_options
@click.pass_context
def schedule_list(ctx: click.Context, **kwargs: Any) -> None:
    """List scheduled triggers.

    Shows all active scheduled triggers. Use --all to include disabled triggers.

    \b
    Examples:
      mng schedule list
      mng schedule list --all
      mng schedule list --json
    """
    _mng_ctx, _output_opts, _opts = setup_command_context(
        ctx=ctx,
        command_name="schedule_list",
        command_class=ScheduleListCliOptions,
    )
    raise NotImplementedError("schedule list is not implemented yet")


# =============================================================================
# run subcommand
# =============================================================================


@schedule.command(name="run")
@click.argument("name", required=True)
@add_common_options
@click.pass_context
def schedule_run(ctx: click.Context, **kwargs: Any) -> None:
    """Run a scheduled trigger immediately.

    Executes the specified trigger's command right now, regardless of its
    cron schedule. Useful for testing triggers before waiting for the
    scheduled time.

    \b
    Examples:
      mng schedule run my-trigger
    """
    _mng_ctx, _output_opts, _opts = setup_command_context(
        ctx=ctx,
        command_name="schedule_run",
        command_class=ScheduleRunCliOptions,
    )
    raise NotImplementedError("schedule run is not implemented yet")


# =============================================================================
# Help Metadata
# =============================================================================


_SCHEDULE_HELP_METADATA = CommandHelpMetadata(
    name="mng-schedule",
    one_line_description="Schedule remote invocations of mng commands",
    synopsis="mng schedule [add|remove|update|list|run] [OPTIONS]",
    description="""Schedule remote invocations of mng commands.

Manage cron-scheduled triggers that run mng commands (create, start, message,
exec) on a specified provider at regular intervals. This is useful for setting
up autonomous agents that run on a recurring schedule.""",
    examples=(
        ("Add a nightly scheduled agent", "mng schedule add --command create --schedule '0 2 * * *' --provider modal"),
        ("List all schedules", "mng schedule list"),
        ("Remove a trigger", "mng schedule remove my-trigger"),
        ("Disable a trigger", "mng schedule update my-trigger --disabled"),
        ("Test a trigger immediately", "mng schedule run my-trigger"),
    ),
    see_also=(
        ("create", "Create a new agent"),
        ("start", "Start an existing agent"),
        ("exec", "Execute a command on an agent"),
    ),
)

register_help_metadata("schedule", _SCHEDULE_HELP_METADATA)

add_pager_help_option(schedule)
