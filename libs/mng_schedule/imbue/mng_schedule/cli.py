from enum import auto
from typing import Any

import click
from click_option_group import optgroup

from imbue.imbue_common.enums import UpperCaseStrEnum
from imbue.mng.cli.common_opts import CommonCliOptions
from imbue.mng.cli.common_opts import add_common_options
from imbue.mng.cli.common_opts import setup_command_context
from imbue.mng.cli.default_command_group import DefaultCommandGroup
from imbue.mng.cli.help_formatter import CommandHelpMetadata
from imbue.mng.cli.help_formatter import add_pager_help_option
from imbue.mng.cli.help_formatter import register_help_metadata

# =============================================================================
# Enums
# =============================================================================


class VerifyMode(UpperCaseStrEnum):
    """Controls post-deploy verification behavior."""

    VERIFY = auto()
    FULL_VERIFY = auto()
    NO_VERIFY = auto()


# =============================================================================
# CLI Options
# =============================================================================


class ScheduleUpdateCliOptions(CommonCliOptions):
    """Shared options for the schedule add and update subcommands."""

    positional_name: str | None
    name: str | None
    command: str | None
    args: str | None
    schedule_cron: str | None
    provider: str | None
    enabled: bool | None
    verify: bool
    full_verify: bool


class ScheduleAddCliOptions(ScheduleUpdateCliOptions):
    """Options for the schedule add subcommand.

    Identical to update, plus an --update flag to allow upserting.
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
# Shared option decorator
# =============================================================================


def _add_trigger_options(command: Any) -> Any:
    """Add trigger definition options shared by add and update commands.

    All options are optional at the click level. Commands that require specific
    options (e.g. add requires --command, --schedule, --provider) should
    validate at runtime.
    """
    # Applied in reverse order (bottom-up per click convention)

    # Optional positional argument for the name (alternative to --name)
    command = click.argument("positional_name", default=None, required=False)(command)

    # Behavior group
    command = optgroup.option(
        "--full-verify",
        is_flag=True,
        help="After deploying, invoke the trigger and let the launched agent run to completion.",
    )(command)
    command = optgroup.option(
        "--verify/--no-verify",
        "verify",
        default=True,
        show_default=True,
        help="After deploying, invoke the trigger to check that it works. The agent is destroyed once it starts successfully.",
    )(command)
    command = optgroup.option(
        "--enabled/--disabled",
        "enabled",
        default=None,
        help="Whether the schedule is enabled.",
    )(command)
    command = optgroup.group("Behavior")(command)

    # Execution group
    command = optgroup.option(
        "--provider",
        default=None,
        help="Provider in which to schedule the call (e.g. 'local', 'modal').",
    )(command)
    command = optgroup.group("Execution")(command)

    # Trigger Definition group
    command = optgroup.option(
        "--schedule",
        "schedule_cron",
        default=None,
        help="Cron schedule expression defining when the command runs (e.g. '0 2 * * *').",
    )(command)
    command = optgroup.option(
        "--args",
        "args",
        default=None,
        help="Arguments to pass to the mng command (as a string).",
    )(command)
    command = optgroup.option(
        "--command",
        "command",
        type=click.Choice(["create", "start", "message", "exec"], case_sensitive=False),
        default=None,
        help="Which mng command to run when triggered.",
    )(command)
    command = optgroup.option(
        "--name",
        default=None,
        help="Name for this scheduled trigger. If not specified, a random name is generated.",
    )(command)
    command = optgroup.group("Trigger Definition")(command)

    return command


def _resolve_positional_name(ctx: click.Context) -> None:
    """Merge the optional positional NAME into the --name option.

    If only the positional is provided, it becomes the --name value.
    If both are provided, raise a UsageError.
    """
    positional = ctx.params.get("positional_name")
    option = ctx.params.get("name")
    if positional and option:
        raise click.UsageError("Cannot specify both a positional NAME and --name.")
    if positional:
        ctx.params["name"] = positional


# =============================================================================
# CLI Group
# =============================================================================


class _ScheduleGroup(DefaultCommandGroup):
    """Schedule group that defaults to 'list' when no subcommand is given."""

    _default_command = "list"


@click.group(name="schedule", cls=_ScheduleGroup)
@add_common_options
@click.pass_context
def schedule(ctx: click.Context, **kwargs: Any) -> None:
    """Schedule remote invocations of mng commands.

    Manage cron-scheduled triggers that run mng commands (create, start,
    message, exec) on a specified provider at regular intervals.

    \b
    Examples:
      mng schedule add --command create --args '--message "do work" --in modal' --schedule "0 2 * * *" --provider modal
      mng schedule list
      mng schedule remove my-trigger
      mng schedule run my-trigger
    """


# =============================================================================
# add subcommand
# =============================================================================


@schedule.command(name="add")
@_add_trigger_options
@optgroup.group("Add-specific")
@optgroup.option(
    "--update",
    is_flag=True,
    help="If a schedule with the same name already exists, update it instead of failing.",
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
    _resolve_positional_name(ctx)
    # New schedules default to enabled. The shared options use None so that
    # update can distinguish "not specified" from "explicitly set".
    if ctx.params.get("enabled") is None:
        ctx.params["enabled"] = True
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
@_add_trigger_options
@add_common_options
@click.pass_context
def schedule_update(ctx: click.Context, **kwargs: Any) -> None:
    """Update an existing scheduled trigger.

    Alias for 'add --update'. Accepts the same options as the add command.
    """
    _resolve_positional_name(ctx)
    ctx.params["update"] = True
    _mng_ctx, _output_opts, _opts = setup_command_context(
        ctx=ctx,
        command_name="schedule_update",
        command_class=ScheduleAddCliOptions,
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
