from typing import assert_never

import click
from click_option_group import optgroup
from loguru import logger

from imbue.imbue_common.pure import pure
from imbue.mngr.api.cleanup import execute_cleanup
from imbue.mngr.api.cleanup import find_agents_for_cleanup
from imbue.mngr.api.data_types import CleanupResult
from imbue.mngr.api.list import AgentInfo
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
from imbue.mngr.config.data_types import OutputOptions
from imbue.mngr.primitives import CleanupAction
from imbue.mngr.primitives import ErrorBehavior
from imbue.mngr.primitives import OutputFormat
from imbue.mngr.utils.duration import parse_duration_to_seconds


class CleanupCliOptions(CommonCliOptions):
    """Options passed from the CLI to the cleanup command.

    Inherits common options (output_format, quiet, verbose, etc.) from CommonCliOptions.

    Note that this class VERY INTENTIONALLY DOES NOT use Field() decorators with descriptions, defaults, etc.
    For that information, see the click.option() and click.argument() decorators on the cleanup() function itself.
    """

    force: bool
    dry_run: bool
    include: tuple[str, ...]
    exclude: tuple[str, ...]
    older_than: str | None
    idle_for: str | None
    tag: tuple[str, ...]
    provider: tuple[str, ...]
    agent_type: tuple[str, ...]
    action: str
    snapshot_before: bool


@click.command(name="cleanup")
@optgroup.group("General")
@optgroup.option(
    "-f",
    "--force",
    "--yes",
    is_flag=True,
    help="Skip confirmation prompts",
)
@optgroup.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be destroyed or stopped without executing",
)
@optgroup.group("Filtering")
@optgroup.option(
    "--include",
    multiple=True,
    help="Include only agents matching this CEL filter (repeatable)",
)
@optgroup.option(
    "--exclude",
    multiple=True,
    help="Exclude agents matching this CEL filter (repeatable)",
)
@optgroup.option(
    "--older-than",
    default=None,
    help="Select agents older than specified duration (e.g., 7d, 24h)",
)
@optgroup.option(
    "--idle-for",
    default=None,
    help="Select agents idle for at least this duration (e.g., 1h, 30m)",
)
@optgroup.option(
    "--tag",
    multiple=True,
    help="Select agents/hosts with this tag (repeatable)",
)
@optgroup.option(
    "--provider",
    multiple=True,
    help="Select hosts from this provider (repeatable)",
)
@optgroup.option(
    "--agent-type",
    multiple=True,
    help="Select this agent type, e.g., claude, codex (repeatable)",
)
@optgroup.group("Actions")
@optgroup.option(
    "--action",
    type=click.Choice(["destroy", "stop"], case_sensitive=False),
    default="destroy",
    show_default=True,
    help="Action to perform on selected agents",
)
@optgroup.option(
    "--destroy",
    "action",
    flag_value="destroy",
    help="Destroy selected agents/hosts (default)",
)
@optgroup.option(
    "--stop",
    "action",
    flag_value="stop",
    help="Stop selected agents instead of destroying",
)
@optgroup.option(
    "--snapshot-before",
    is_flag=True,
    help="Create snapshots before destroying or stopping [future]",
)
@add_common_options
@click.pass_context
def cleanup(ctx: click.Context, **kwargs) -> None:
    """Destroy or stop agents and hosts to free up resources.

    When running interactively, provides an interactive interface for reviewing
    and selecting agents. Use --yes to skip prompts.

    Examples:

      mngr cleanup

      mngr cleanup --dry-run --yes

      mngr cleanup --older-than 7d --yes

      mngr cleanup --stop --idle-for 1h --yes

      mngr cleanup --provider docker --yes
    """
    try:
        _cleanup_impl(ctx, **kwargs)
    except AbortError as e:
        logger.error("Aborted: {}", e.message)
        ctx.exit(1)


def _cleanup_impl(ctx: click.Context, **kwargs) -> None:
    """Implementation of the cleanup command."""
    mngr_ctx, output_opts, opts = setup_command_context(
        ctx=ctx,
        command_name="cleanup",
        command_class=CleanupCliOptions,
    )
    logger.debug("Started cleanup command")

    # --snapshot-before is a future feature
    if opts.snapshot_before:
        raise NotImplementedError("The --snapshot-before option is not yet implemented.")

    # Resolve the action
    action = CleanupAction(opts.action.upper())
    error_behavior = ErrorBehavior.CONTINUE

    # Build CEL filters from convenience options
    include_filters, exclude_filters = _build_cel_filters_from_options(opts)

    # Find agents matching the filters
    emit_info("Finding agents...", output_opts.output_format)
    agents = find_agents_for_cleanup(
        mngr_ctx=mngr_ctx,
        include_filters=tuple(include_filters),
        exclude_filters=tuple(exclude_filters),
        error_behavior=error_behavior,
    )

    if not agents:
        _emit_no_agents_found(output_opts)
        return

    # Interactive selection or non-interactive path
    if mngr_ctx.is_interactive and not opts.force and not opts.dry_run:
        selected_agents = _run_interactive_selection(agents, action)
        if not selected_agents:
            emit_info("No agents selected.", output_opts.output_format)
            return
    else:
        selected_agents = agents

    # Dry run: just show what would happen
    if opts.dry_run:
        _emit_dry_run_output(selected_agents, action, output_opts)
        return

    # Confirm if not forced and not interactive (interactive already confirmed via selection)
    if not opts.force and not mngr_ctx.is_interactive:
        _emit_agent_list(selected_agents, action, output_opts)
        if not click.confirm("Are you sure you want to continue?"):
            raise click.Abort()

    # Execute the cleanup action
    match action:
        case CleanupAction.DESTROY:
            action_label = "Destroying"
        case CleanupAction.STOP:
            action_label = "Stopping"
        case _ as unreachable:
            assert_never(unreachable)
    emit_info(f"{action_label} {len(selected_agents)} agent(s)...", output_opts.output_format)

    result = execute_cleanup(
        mngr_ctx=mngr_ctx,
        agents=selected_agents,
        action=action,
        is_dry_run=False,
        error_behavior=error_behavior,
    )

    # Output results
    _emit_result(result, output_opts)


@pure
def _build_cel_filters_from_options(
    opts: CleanupCliOptions,
) -> tuple[list[str], list[str]]:
    """Build CEL include/exclude filters from convenience CLI options."""
    include_filters = list(opts.include)
    exclude_filters = list(opts.exclude)

    # --older-than DURATION -> age > N (seconds)
    if opts.older_than is not None:
        older_than_seconds = parse_duration_to_seconds(opts.older_than)
        include_filters.append(f"age > {older_than_seconds}")

    # --idle-for DURATION -> idle > N (seconds)
    if opts.idle_for is not None:
        idle_for_seconds = parse_duration_to_seconds(opts.idle_for)
        include_filters.append(f"idle > {idle_for_seconds}")

    # --provider PROVIDER -> host.provider == "PROVIDER" (repeatable, OR'd)
    if opts.provider:
        provider_conditions = [f'host.provider == "{p}"' for p in opts.provider]
        if len(provider_conditions) == 1:
            include_filters.append(provider_conditions[0])
        else:
            include_filters.append("(" + " || ".join(provider_conditions) + ")")

    # --agent-type TYPE -> type == "TYPE" (repeatable, OR'd)
    if opts.agent_type:
        type_conditions = [f'type == "{t}"' for t in opts.agent_type]
        if len(type_conditions) == 1:
            include_filters.append(type_conditions[0])
        else:
            include_filters.append("(" + " || ".join(type_conditions) + ")")

    # --tag TAG -> host.tags (repeatable)
    if opts.tag:
        for tag in opts.tag:
            if "=" in tag:
                key, value = tag.split("=", 1)
                include_filters.append(f'host.tags.{key} == "{value}"')
            else:
                include_filters.append(f'host.tags.{tag} == "true"')

    return include_filters, exclude_filters


def _run_interactive_selection(
    agents: list[AgentInfo],
    action: CleanupAction,
) -> list[AgentInfo]:
    """Show a numbered list of agents and let the user select which to act on."""
    match action:
        case CleanupAction.DESTROY:
            action_verb = "destroy"
        case CleanupAction.STOP:
            action_verb = "stop"
        case _ as unreachable:
            assert_never(unreachable)
    logger.info("\nFound {} agent(s). Select which to {}:\n", len(agents), action_verb)

    for idx, agent in enumerate(agents, start=1):
        state_str = agent.state.value
        provider_str = str(agent.host.provider_name)
        host_state = agent.host.state.value if agent.host.state else "unknown"
        logger.info(
            "  [{}] {} (type={}, state={}, provider={}, host_state={})",
            idx,
            agent.name,
            agent.type,
            state_str,
            provider_str,
            host_state,
        )

    logger.info("")
    logger.info("Enter selection: numbers (1,3,5), ranges (1-3), 'all', or 'none'")

    selection = click.prompt("Selection", type=str, default="none")
    return _parse_selection(selection, agents)


@pure
def _parse_selection(selection: str, agents: list[AgentInfo]) -> list[AgentInfo]:
    """Parse a user selection string into a list of agents."""
    stripped = selection.strip().lower()

    if stripped == "none" or stripped == "":
        return []

    if stripped == "all":
        return list(agents)

    # Parse comma-separated values, each of which can be a number or range
    selected_indices: set[int] = set()
    parts = stripped.split(",")
    for part in parts:
        stripped_part = part.strip()
        if "-" in stripped_part:
            # Range like "1-3"
            range_parts = stripped_part.split("-", 1)
            try:
                range_start = int(range_parts[0].strip())
                range_end = int(range_parts[1].strip())
                for idx in range(range_start, range_end + 1):
                    if 1 <= idx <= len(agents):
                        selected_indices.add(idx)
            except ValueError:
                continue
        else:
            try:
                idx = int(stripped_part)
                if 1 <= idx <= len(agents):
                    selected_indices.add(idx)
            except ValueError:
                continue

    # Convert 1-based indices to agents
    return [agents[idx - 1] for idx in sorted(selected_indices)]


def _emit_no_agents_found(output_opts: OutputOptions) -> None:
    """Output message when no agents are found."""
    match output_opts.output_format:
        case OutputFormat.JSON:
            emit_final_json({"agents": [], "message": "No agents found"})
        case OutputFormat.JSONL:
            emit_event("info", {"message": "No agents found"}, OutputFormat.JSONL)
        case OutputFormat.HUMAN:
            logger.info("No agents found matching the specified filters")
        case _ as unreachable:
            assert_never(unreachable)


def _emit_dry_run_output(
    agents: list[AgentInfo],
    action: CleanupAction,
    output_opts: OutputOptions,
) -> None:
    """Output what would happen in a dry run."""
    match action:
        case CleanupAction.DESTROY:
            action_verb = "Would destroy"
        case CleanupAction.STOP:
            action_verb = "Would stop"
        case _ as unreachable:
            assert_never(unreachable)
    agent_data = [
        {
            "name": str(agent.name),
            "id": str(agent.id),
            "type": agent.type,
            "state": agent.state.value,
            "host_id": str(agent.host.id),
            "provider": str(agent.host.provider_name),
        }
        for agent in agents
    ]

    match output_opts.output_format:
        case OutputFormat.JSON:
            emit_final_json({"action": action.value.lower(), "dry_run": True, "agents": agent_data})
        case OutputFormat.JSONL:
            emit_event("dry_run", {"action": action.value.lower(), "agents": agent_data}, OutputFormat.JSONL)
        case OutputFormat.HUMAN:
            logger.info("\n{} {} agent(s):", action_verb, len(agents))
            for agent in agents:
                logger.info(
                    "  - {} (type={}, state={}, provider={})",
                    agent.name,
                    agent.type,
                    agent.state.value,
                    agent.host.provider_name,
                )
        case _ as unreachable:
            assert_never(unreachable)


def _emit_agent_list(
    agents: list[AgentInfo],
    action: CleanupAction,
    output_opts: OutputOptions,
) -> None:
    """Output the list of agents that will be acted on."""
    if output_opts.output_format != OutputFormat.HUMAN:
        return
    match action:
        case CleanupAction.DESTROY:
            action_past_tense = "destroyed"
        case CleanupAction.STOP:
            action_past_tense = "stopped"
        case _ as unreachable:
            assert_never(unreachable)
    logger.info("\nThe following {} agent(s) will be {}:", len(agents), action_past_tense)
    for agent in agents:
        logger.info("  - {} (provider={})", agent.name, agent.host.provider_name)
    logger.info("")


def _emit_result(
    result: CleanupResult,
    output_opts: OutputOptions,
) -> None:
    """Output the final result of the cleanup operation."""
    result_data = {
        "destroyed_agents": [str(n) for n in result.destroyed_agents],
        "stopped_agents": [str(n) for n in result.stopped_agents],
        "errors": result.errors,
        "destroyed_count": len(result.destroyed_agents),
        "stopped_count": len(result.stopped_agents),
        "error_count": len(result.errors),
    }

    match output_opts.output_format:
        case OutputFormat.JSON:
            emit_final_json(result_data)
        case OutputFormat.JSONL:
            emit_event("cleanup_result", result_data, OutputFormat.JSONL)
        case OutputFormat.HUMAN:
            if result.destroyed_agents:
                logger.info("Successfully destroyed {} agent(s)", len(result.destroyed_agents))
                for name in result.destroyed_agents:
                    logger.info("  - {}", name)
            if result.stopped_agents:
                logger.info("Successfully stopped {} agent(s)", len(result.stopped_agents))
                for name in result.stopped_agents:
                    logger.info("  - {}", name)
            if result.errors:
                logger.warning("{} error(s) occurred:", len(result.errors))
                for error in result.errors:
                    logger.warning("  - {}", error)
            if not result.destroyed_agents and not result.stopped_agents:
                logger.info("No agents were affected")
        case _ as unreachable:
            assert_never(unreachable)


# Register help metadata for git-style help formatting
_CLEANUP_HELP_METADATA = CommandHelpMetadata(
    name="mngr-cleanup",
    one_line_description="Destroy or stop agents and hosts to free up resources",
    synopsis="mngr [cleanup|clean] [--destroy|--stop] [--older-than DURATION] [--idle-for DURATION] "
    "[--provider PROVIDER] [--agent-type TYPE] [--tag TAG] [-f|--force|--yes] [--dry-run]",
    description="""Destroy or stop agents and hosts to free up resources.

When running interactively, provides an interactive interface for reviewing
and selecting agents. Use --yes to skip confirmation prompts.

Convenience filters like --older-than and --idle-for are translated into CEL
expressions internally, so they can be combined with --include and --exclude
for precise control.

For automatic garbage collection of unused resources without interaction,
see `mngr gc`.""",
    aliases=("clean",),
    examples=(
        ("Interactive cleanup (default)", "mngr cleanup"),
        ("Preview what would be destroyed", "mngr cleanup --dry-run --yes"),
        ("Destroy agents older than 7 days", "mngr cleanup --older-than 7d --yes"),
        ("Stop idle agents", "mngr cleanup --stop --idle-for 1h --yes"),
        ("Destroy Docker agents only", "mngr cleanup --provider docker --yes"),
        ("Destroy by agent type", "mngr cleanup --agent-type codex --yes"),
    ),
    see_also=(
        ("destroy", "Destroy specific agents by name"),
        ("stop", "Stop specific agents by name"),
        ("gc", "Garbage collect orphaned resources"),
        ("list", "List agents with filtering"),
    ),
)

register_help_metadata("cleanup", _CLEANUP_HELP_METADATA)
# Also register under alias for consistent help output
for alias in _CLEANUP_HELP_METADATA.aliases:
    register_help_metadata(alias, _CLEANUP_HELP_METADATA)

# Add pager-enabled help option to the cleanup command
add_pager_help_option(cleanup)
