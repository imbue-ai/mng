import sys
from typing import Any
from typing import Final
from typing import assert_never
from uuid import uuid4

import click
from click_option_group import optgroup
from loguru import logger
from tabulate import tabulate

from imbue.imbue_common.errors import SwitchError
from imbue.imbue_common.logging import log_span
from imbue.mng.cli.common_opts import CommonCliOptions
from imbue.mng.cli.common_opts import add_common_options
from imbue.mng.cli.common_opts import setup_command_context
from imbue.mng.cli.default_command_group import DefaultCommandGroup
from imbue.mng.cli.help_formatter import CommandHelpMetadata
from imbue.mng.cli.help_formatter import add_pager_help_option
from imbue.mng.cli.help_formatter import register_help_metadata
from imbue.mng.cli.output_helpers import emit_final_json
from imbue.mng.cli.output_helpers import write_human_line
from imbue.mng.primitives import OutputFormat
from imbue.mng_schedule.data_types import ScheduleCreationRecord
from imbue.mng_schedule.data_types import ScheduleTriggerDefinition
from imbue.mng_schedule.data_types import ScheduledMngCommand
from imbue.mng_schedule.data_types import VerifyMode
from imbue.mng_schedule.errors import ScheduleDeployError
from imbue.mng_schedule.implementations.modal.deploy import deploy_schedule
from imbue.mng_schedule.implementations.modal.deploy import list_schedule_creation_records
from imbue.mng_schedule.implementations.modal.deploy import load_modal_provider_instance
from imbue.mng_schedule.implementations.modal.deploy import resolve_git_ref

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
    verify: str
    git_image_hash: str | None


class ScheduleAddCliOptions(ScheduleUpdateCliOptions):
    """Options for the schedule add subcommand.

    These are exactly the same as update--the only difference is whether we error if the name already exists.
    Name is optional here (unlike update) because a random name can be generated.
    """

    name: str | None
    update: bool


class ScheduleRemoveCliOptions(CommonCliOptions):
    """Options for the schedule remove subcommand."""

    names: tuple[str, ...]
    force: bool


class ScheduleListCliOptions(CommonCliOptions):
    """Options for the schedule list subcommand."""

    all_schedules: bool
    provider: str


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
        "--verify",
        type=click.Choice(["none", "quick", "full"], case_sensitive=False),
        default="quick",
        show_default=True,
        help="Post-deploy verification: 'none' skips, 'quick' invokes and destroys agent, 'full' lets agent run to completion.",
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

    # Code Packaging group
    command = optgroup.option(
        "--git-image-hash",
        "git_image_hash",
        default=None,
        help="Git commit hash (or ref like HEAD) to package project code from. Required for modal provider.",
    )(command)
    command = optgroup.group("Code Packaging")(command)

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
    mng_ctx, _output_opts, opts = setup_command_context(
        ctx=ctx,
        command_name="schedule_add",
        command_class=ScheduleAddCliOptions,
    )

    # Validate required options for add
    if opts.command is None:
        raise click.UsageError("--command is required for schedule add")
    if opts.schedule_cron is None:
        raise click.UsageError("--schedule is required for schedule add")
    if opts.provider is None:
        raise click.UsageError("--provider is required for schedule add")
    if opts.git_image_hash is None:
        raise click.UsageError(
            "--git-image-hash is required when provider is 'modal'. Use HEAD to package the current commit."
        )

    # Load and validate the provider instance
    try:
        provider = load_modal_provider_instance(opts.provider, mng_ctx)
    except ScheduleDeployError as e:
        raise click.ClickException(str(e)) from e

    # Generate name if not provided
    trigger_name = opts.name if opts.name else f"trigger-{uuid4().hex[:8]}"

    # Resolve git ref to full SHA (git_image_hash is guaranteed non-None by validation above)
    resolved_hash = resolve_git_ref(opts.git_image_hash)

    trigger = ScheduleTriggerDefinition(
        name=trigger_name,
        command=ScheduledMngCommand(opts.command.upper()),
        args=opts.args or "",
        schedule_cron=opts.schedule_cron,
        provider=opts.provider,
        is_enabled=opts.enabled if opts.enabled is not None else True,
        git_image_hash=resolved_hash,
    )

    # Resolve verification mode from CLI option.
    # Only apply verification for create commands (other commands don't produce agents).
    verify_mode = VerifyMode(opts.verify.upper())
    if verify_mode != VerifyMode.NONE and trigger.command != ScheduledMngCommand.CREATE:
        logger.debug(
            "Skipping verification for command '{}': only applicable to 'create' commands",
            trigger.command,
        )
        verify_mode = VerifyMode.NONE

    try:
        app_name = deploy_schedule(trigger, mng_ctx, provider=provider, verify_mode=verify_mode, sys_argv=sys.argv)
    except ScheduleDeployError as e:
        raise click.ClickException(str(e)) from e

    logger.info("Schedule '{}' deployed as Modal app '{}'", trigger_name, app_name)
    click.echo(f"Deployed schedule '{trigger_name}' as Modal app '{app_name}'")


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
@optgroup.option(
    "--provider",
    default="modal",
    show_default=True,
    help="Provider instance to list schedules from.",
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
    mng_ctx, output_opts, opts = setup_command_context(
        ctx=ctx,
        command_name="schedule_list",
        command_class=ScheduleListCliOptions,
    )

    # Load the provider instance
    try:
        provider = load_modal_provider_instance(opts.provider, mng_ctx)
    except ScheduleDeployError as e:
        raise click.ClickException(str(e)) from e

    with log_span("Listing schedule creation records"):
        records = list_schedule_creation_records(provider)

    # Filter out disabled schedules unless --all is specified
    if not opts.all_schedules:
        records = [r for r in records if r.trigger.is_enabled]

    # Sort by creation time (oldest first)
    records_sorted = sorted(records, key=lambda r: r.created_at)

    match output_opts.output_format:
        case OutputFormat.JSON:
            _emit_schedule_list_json(records_sorted)
        case OutputFormat.JSONL:
            _emit_schedule_list_jsonl(records_sorted)
        case OutputFormat.HUMAN:
            _emit_schedule_list_human(records_sorted)
        case _ as unreachable:
            assert_never(unreachable)


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
# Output helpers for schedule list
# =============================================================================


_SCHEDULE_LIST_DISPLAY_FIELDS: Final[tuple[str, ...]] = (
    "name",
    "command",
    "schedule",
    "enabled",
    "provider",
    "git_hash",
    "created_at",
    "hostname",
)

_SCHEDULE_LIST_HEADERS: Final[dict[str, str]] = {
    "name": "NAME",
    "command": "COMMAND",
    "schedule": "SCHEDULE",
    "enabled": "ENABLED",
    "provider": "PROVIDER",
    "git_hash": "GIT HASH",
    "created_at": "CREATED",
    "hostname": "HOST",
}


def _get_schedule_field_value(record: ScheduleCreationRecord, field: str) -> str:
    """Extract a display value from a ScheduleCreationRecord."""
    match field:
        case "name":
            return record.trigger.name
        case "command":
            return record.trigger.command.value.lower()
        case "schedule":
            return record.trigger.schedule_cron
        case "enabled":
            return "yes" if record.trigger.is_enabled else "no"
        case "provider":
            return record.trigger.provider
        case "git_hash":
            return record.trigger.git_image_hash[:12]
        case "created_at":
            return record.created_at.strftime("%Y-%m-%d %H:%M")
        case "hostname":
            return record.hostname
        case _:
            raise SwitchError(f"Unknown schedule display field: {field}")


def _emit_schedule_list_human(records: list[ScheduleCreationRecord]) -> None:
    """Emit human-readable table output for schedule list."""
    if not records:
        write_human_line("No schedules found")
        return

    headers = [_SCHEDULE_LIST_HEADERS[f] for f in _SCHEDULE_LIST_DISPLAY_FIELDS]
    rows: list[list[str]] = []
    for record in records:
        row = [_get_schedule_field_value(record, f) for f in _SCHEDULE_LIST_DISPLAY_FIELDS]
        rows.append(row)

    table = tabulate(rows, headers=headers, tablefmt="plain")
    write_human_line("\n" + table)


def _emit_schedule_list_json(records: list[ScheduleCreationRecord]) -> None:
    """Emit JSON output for schedule list."""
    data = {
        "schedules": [record.model_dump(mode="json") for record in records],
    }
    emit_final_json(data)


def _emit_schedule_list_jsonl(records: list[ScheduleCreationRecord]) -> None:
    """Emit JSONL output for schedule list."""
    for record in records:
        emit_final_json(record.model_dump(mode="json"))


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
