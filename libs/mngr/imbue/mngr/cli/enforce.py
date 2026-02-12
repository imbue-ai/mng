from typing import assert_never

import click
from click_option_group import optgroup
from loguru import logger

from imbue.mngr.api.enforce import EnforceAction
from imbue.mngr.api.enforce import EnforceResult
from imbue.mngr.api.enforce import enforce as api_enforce
from imbue.mngr.api.providers import get_selected_providers
from imbue.mngr.cli.common_opts import CommonCliOptions
from imbue.mngr.cli.common_opts import add_common_options
from imbue.mngr.cli.common_opts import setup_command_context
from imbue.mngr.cli.help_formatter import CommandHelpMetadata
from imbue.mngr.cli.help_formatter import add_pager_help_option
from imbue.mngr.cli.help_formatter import register_help_metadata
from imbue.mngr.cli.output_helpers import AbortError
from imbue.mngr.cli.output_helpers import emit_event
from imbue.mngr.cli.output_helpers import emit_final_json
from imbue.mngr.cli.output_helpers import emit_info
from imbue.mngr.cli.watch_mode import run_watch_loop
from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.config.data_types import OutputOptions
from imbue.mngr.primitives import ErrorBehavior
from imbue.mngr.primitives import OutputFormat


class EnforceCliOptions(CommonCliOptions):
    """Options passed from the CLI to the enforce command.

    This captures all the click parameters so we can pass them as a single object
    to helper functions instead of passing dozens of individual parameters.

    Inherits common options (output_format, quiet, verbose, etc.) from CommonCliOptions.

    Note that this class VERY INTENTIONALLY DOES NOT use Field() decorators with descriptions, defaults, etc.
    For that information, see the click.option() and click.argument() decorators on the enforce() function itself.
    """

    check_idle: bool
    check_timeouts: bool
    building_timeout: int
    starting_timeout: int
    stopping_timeout: int
    watch: int | None
    dry_run: bool
    on_error: str
    all_providers: bool
    provider: tuple[str, ...]


@click.command(name="enforce")
@optgroup.group("Checks")
@optgroup.option(
    "--check-idle/--no-check-idle",
    default=True,
    show_default=True,
    help="Check for hosts that have exceeded their idle timeouts",
)
@optgroup.option(
    "--check-timeouts/--no-check-timeouts",
    default=True,
    show_default=True,
    help="Check for hosts stuck in transitory states (building, starting, stopping)",
)
@optgroup.group("Timeout Configuration")
@optgroup.option(
    "--building-timeout",
    type=int,
    default=1800,
    show_default=True,
    help="Seconds before a BUILDING host is considered stuck",
)
@optgroup.option(
    "--starting-timeout",
    type=int,
    default=900,
    show_default=True,
    help="Seconds before a STARTING host is considered stuck",
)
@optgroup.option(
    "--stopping-timeout",
    type=int,
    default=600,
    show_default=True,
    help="Seconds before a STOPPING host is considered stuck",
)
@optgroup.group("Scope")
@optgroup.option(
    "--all-providers",
    is_flag=True,
    help="Enforce across all providers",
)
@optgroup.option(
    "--provider",
    multiple=True,
    help="Enforce for a specific provider (repeatable)",
)
@optgroup.group("Safety")
@optgroup.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be enforced without taking action",
)
@optgroup.option(
    "--on-error",
    type=click.Choice(["abort", "continue"], case_sensitive=False),
    default="abort",
    help="What to do when errors occur: abort (stop immediately) or continue (keep going)",
)
@optgroup.option(
    "-w",
    "--watch",
    type=int,
    help="Re-run enforcement checks at the specified interval (seconds)",
)
@add_common_options
@click.pass_context
def enforce(ctx: click.Context, **kwargs) -> None:
    """Enforce host idle timeouts and detect stuck state transitions.

    Ensures that no hosts have exceeded their idle timeouts and that no hosts
    are stuck in transitory states (building, starting, stopping).

    This command is intended to be run periodically from a trusted location
    as a backup mechanism for in-host idle detection.

    Examples:

      mngr enforce --dry-run

      mngr enforce --check-idle --no-check-timeouts

      mngr enforce --watch 300

      mngr enforce --starting-timeout 1200 --provider docker
    """
    try:
        _enforce_impl(ctx, **kwargs)
    except AbortError as e:
        logger.error("Aborted: {}", e.message)
        ctx.exit(1)


def _enforce_impl(ctx: click.Context, **kwargs) -> None:
    """Implementation of enforce command (extracted for exception handling)."""
    mngr_ctx, output_opts, opts = setup_command_context(
        ctx=ctx,
        command_name="enforce",
        command_class=EnforceCliOptions,
    )
    logger.debug("Started enforce command")

    # Validate at least one check is enabled
    if not opts.check_idle and not opts.check_timeouts:
        error_msg = "No checks enabled. Use --check-idle and/or --check-timeouts."
        match output_opts.output_format:
            case OutputFormat.JSON:
                emit_final_json({"error": error_msg, "exit_code": 1})
            case OutputFormat.JSONL:
                emit_event("error", {"message": error_msg, "exit_code": 1}, OutputFormat.JSONL)
            case OutputFormat.HUMAN:
                logger.error(error_msg)
            case _ as unreachable:
                assert_never(unreachable)
        ctx.exit(1)

    # Watch mode or single iteration
    if opts.watch:
        try:
            run_watch_loop(
                iteration_fn=lambda: _run_enforce_iteration(mngr_ctx=mngr_ctx, opts=opts, output_opts=output_opts),
                interval_seconds=opts.watch,
                on_error_continue=True,
            )
        except KeyboardInterrupt:
            logger.info("\nWatch mode stopped")
            return
    else:
        _run_enforce_iteration(mngr_ctx=mngr_ctx, opts=opts, output_opts=output_opts)


def _run_enforce_iteration(mngr_ctx: MngrContext, opts: EnforceCliOptions, output_opts: OutputOptions) -> None:
    """Run a single enforcement iteration."""
    error_behavior = ErrorBehavior(opts.on_error.upper())
    providers = get_selected_providers(
        mngr_ctx=mngr_ctx,
        is_all_providers=opts.all_providers,
        provider_names=opts.provider,
    )

    # Emit info about what checks are enabled
    if opts.check_idle:
        emit_info("Checking for idle hosts...", output_opts.output_format)
    if opts.check_timeouts:
        emit_info("Checking for stuck state transitions...", output_opts.output_format)

    # Call the API
    result = api_enforce(
        providers=providers,
        is_check_idle=opts.check_idle,
        is_check_timeouts=opts.check_timeouts,
        building_timeout_seconds=opts.building_timeout,
        starting_timeout_seconds=opts.starting_timeout,
        stopping_timeout_seconds=opts.stopping_timeout,
        is_dry_run=opts.dry_run,
        error_behavior=error_behavior,
    )

    # Emit events for each action
    for action in result.actions:
        _emit_action(action=action, output_format=output_opts.output_format)

    # Emit final summary
    _emit_final_summary(result=result, output_format=output_opts.output_format, is_dry_run=opts.dry_run)


def _emit_action(action: EnforceAction, output_format: OutputFormat) -> None:
    """Emit an enforcement action event."""
    event_data = {
        "message": _format_action_message(action),
        "host_id": str(action.host_id),
        "host_name": action.host_name,
        "provider_name": str(action.provider_name),
        "host_state": str(action.host_state),
        "action": action.action,
        "reason": action.reason,
        "dry_run": action.is_dry_run,
    }
    emit_event("enforce_action", event_data, output_format)


def _format_action_message(action: EnforceAction) -> str:
    """Format a human-readable message for an enforcement action."""
    prefix = "Would" if action.is_dry_run else "Executed"
    action_label = "stop" if action.action == "stop_host" else "destroy"
    return f"{prefix} {action_label} {action.host_name} ({action.provider_name}): {action.reason}"


def _emit_final_summary(result: EnforceResult, output_format: OutputFormat, is_dry_run: bool) -> None:
    """Emit the final summary for enforcement results."""
    match output_format:
        case OutputFormat.JSON:
            _emit_json_summary(result, is_dry_run)
        case OutputFormat.HUMAN:
            _emit_human_summary(result, is_dry_run)
        case OutputFormat.JSONL:
            _emit_jsonl_summary(result, is_dry_run)
        case _ as unreachable:
            assert_never(unreachable)


def _emit_json_summary(result: EnforceResult, is_dry_run: bool) -> None:
    """Emit JSON summary."""
    output_data = {
        "actions": [a.model_dump(mode="json") for a in result.actions],
        "hosts_checked": result.hosts_checked,
        "idle_violations": result.idle_violations,
        "timeout_violations": result.timeout_violations,
        "errors": result.errors,
        "dry_run": is_dry_run,
    }
    emit_final_json(output_data)


def _emit_human_summary(result: EnforceResult, is_dry_run: bool) -> None:
    """Emit human-readable summary."""
    logger.info("")
    if is_dry_run:
        logger.info("Enforcement (Dry Run)")
    else:
        logger.info("Enforcement Results")
    logger.info("=" * 40)

    logger.info("\nHosts checked: {}", result.hosts_checked)

    total_actions = len(result.actions)

    if result.idle_violations > 0:
        logger.info("Idle violations: {}", result.idle_violations)

    if result.timeout_violations > 0:
        logger.info("Timeout violations: {}", result.timeout_violations)

    if total_actions == 0:
        logger.info("\nNo enforcement actions needed")
    else:
        action_word = "Would take" if is_dry_run else "Took"
        logger.info("\n{} {} enforcement action(s)", action_word, total_actions)

    if result.errors:
        logger.info("\nErrors:")
        for error in result.errors:
            logger.info("  - {}", error)


def _emit_jsonl_summary(result: EnforceResult, is_dry_run: bool) -> None:
    """Emit JSONL summary event."""
    event = {
        "event": "summary",
        "hosts_checked": result.hosts_checked,
        "idle_violations": result.idle_violations,
        "timeout_violations": result.timeout_violations,
        "total_actions": len(result.actions),
        "errors_count": len(result.errors),
        "errors": result.errors,
        "dry_run": is_dry_run,
    }
    emit_event("summary", event, OutputFormat.JSONL)


# Register help metadata for git-style help formatting
_ENFORCE_HELP_METADATA = CommandHelpMetadata(
    name="mngr-enforce",
    one_line_description="Enforce host idle timeouts and detect stuck state transitions",
    synopsis="mngr enforce [OPTIONS]",
    description="""Enforce host idle timeouts and detect stuck state transitions.

Ensures that no hosts have exceeded their idle timeouts and that no hosts
are stuck in transitory states (building, starting, stopping). This command
is intended to be run periodically from a trusted location as a backup
mechanism for in-host idle detection.

For untrusted hosts where the in-host idle detection script may be tampered
with, this command provides an external enforcement mechanism that runs from
the user's local machine.""",
    examples=(
        ("Preview enforcement actions (dry run)", "mngr enforce --dry-run"),
        ("Check only idle hosts", "mngr enforce --check-idle --no-check-timeouts"),
        ("Run enforcement every 5 minutes", "mngr enforce --watch 300"),
        ("Custom timeout for starting hosts", "mngr enforce --starting-timeout 1200 --provider docker"),
    ),
    see_also=(
        ("gc", "Garbage collect unused resources"),
        ("list", "List hosts and agents"),
        ("stop", "Stop a host manually"),
    ),
)

register_help_metadata("enforce", _ENFORCE_HELP_METADATA)

# Add pager-enabled help option to the enforce command
add_pager_help_option(enforce)
