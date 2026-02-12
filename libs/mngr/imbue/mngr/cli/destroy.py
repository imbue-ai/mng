from typing import NamedTuple
from typing import assert_never

import click
from click_option_group import optgroup
from loguru import logger

from imbue.mngr.api.data_types import GcResourceTypes
from imbue.mngr.api.gc import gc as api_gc
from imbue.mngr.api.list import list_agents
from imbue.mngr.api.providers import get_all_provider_instances
from imbue.mngr.api.providers import get_provider_instance
from imbue.mngr.cli.common_opts import CommonCliOptions
from imbue.mngr.cli.common_opts import add_common_options
from imbue.mngr.cli.common_opts import setup_command_context
from imbue.mngr.cli.help_formatter import CommandHelpMetadata
from imbue.mngr.cli.help_formatter import add_pager_help_option
from imbue.mngr.cli.help_formatter import register_help_metadata
from imbue.mngr.cli.output_helpers import emit_event
from imbue.mngr.cli.output_helpers import emit_final_json
from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.config.data_types import OutputOptions
from imbue.mngr.errors import AgentNotFoundError
from imbue.mngr.errors import HostOfflineError
from imbue.mngr.errors import MngrError
from imbue.mngr.errors import UserInputError
from imbue.mngr.interfaces.agent import AgentInterface
from imbue.mngr.interfaces.host import HostInterface
from imbue.mngr.interfaces.host import OnlineHostInterface
from imbue.mngr.interfaces.provider_instance import ProviderInstanceInterface
from imbue.mngr.primitives import AgentName
from imbue.mngr.primitives import ErrorBehavior
from imbue.mngr.primitives import OutputFormat


class OfflineHostToDestroy(NamedTuple):
    """An offline host where all agents are targeted for destruction."""

    host: HostInterface
    provider: ProviderInstanceInterface
    agent_names: list[AgentName]


# FIXME: neither this nor the above should not be using NamedTuple! Just use our FrozenModel like the rest of the codebase...
#  Also, this class should also have an online_hosts field, and the below logic should be updated to allow directly specification of hosts to destroy
class DestroyTargets(NamedTuple):
    """Result of finding agents/hosts to destroy."""

    online_agents: list[tuple[AgentInterface, OnlineHostInterface]]
    offline_hosts: list[OfflineHostToDestroy]


def get_agent_name_from_session(session_name: str, prefix: str) -> str | None:
    """Extract the agent name from a tmux session name.

    The session name is expected to be in the format "{prefix}{agent_name}".
    Returns the agent name if the session matches the prefix, or None if the
    session name doesn't match the expected prefix format.
    """
    if not session_name:
        logger.debug("Failed to extract agent name: empty session name provided")
        return None

    # Check if the session name starts with our prefix
    if not session_name.startswith(prefix):
        logger.debug(
            "Failed to extract agent name: session name '{}' doesn't start with mngr prefix '{}'",
            session_name,
            prefix,
        )
        return None

    # Extract the agent name by removing the prefix
    agent_name = session_name[len(prefix) :]
    if not agent_name:
        logger.debug(
            "Failed to extract agent name: session name '{}' has empty agent name after stripping prefix", session_name
        )
        return None

    logger.debug("Extracted agent name '{}' from session '{}'", agent_name, session_name)
    return agent_name


class DestroyCliOptions(CommonCliOptions):
    """Options passed from the CLI to the destroy command.

    This captures all the click parameters so we can pass them as a single object
    to helper functions instead of passing dozens of individual parameters.

    Inherits common options (output_format, quiet, verbose, etc.) from CommonCliOptions.

    Note that this class VERY INTENTIONALLY DOES NOT use Field() decorators with descriptions, defaults, etc.
    For that information, see the click.option() and click.argument() decorators on the destroy() function itself.
    """

    agents: tuple[str, ...]
    agent_list: tuple[str, ...]
    force: bool
    destroy_all: bool
    dry_run: bool
    gc: bool
    sessions: tuple[str, ...]
    # Planned features (not yet implemented)
    include: tuple[str, ...]
    exclude: tuple[str, ...]
    stdin: bool


@click.command(name="destroy")
@click.argument("agents", nargs=-1, required=False)
@optgroup.group("Target Selection")
@optgroup.option(
    "--agent",
    "agent_list",
    multiple=True,
    help="Agent name or ID to destroy (can be specified multiple times)",
)
@optgroup.option(
    "-a",
    "--all",
    "--all-agents",
    "destroy_all",
    is_flag=True,
    help="Destroy all agents",
)
@optgroup.option(
    "--session",
    "sessions",
    multiple=True,
    help="Tmux session name to destroy (can be specified multiple times). The agent name is extracted by "
    "stripping the configured prefix from the session name.",
)
@optgroup.option(
    "--include",
    multiple=True,
    help="Filter agents to destroy by CEL expression (repeatable). [future]",
)
@optgroup.option(
    "--exclude",
    multiple=True,
    help="Exclude agents matching CEL expression from destruction (repeatable). [future]",
)
@optgroup.option(
    "--stdin",
    is_flag=True,
    help="Read agent names/IDs from stdin, one per line. [future]",
)
@optgroup.group("Behavior")
@optgroup.option(
    "-f",
    "--force",
    is_flag=True,
    help="Skip confirmation prompts and force destroy running agents",
)
@optgroup.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be destroyed without actually destroying",
)
@optgroup.option(
    "--gc/--no-gc",
    default=True,
    help="Run garbage collection after destroying agents to clean up orphaned resources (default: enabled)",
)
@add_common_options
@click.pass_context
def destroy(ctx: click.Context, **kwargs) -> None:
    """Destroy agent(s) and clean up resources.

    When the last agent on a host is destroyed, the host itself is also destroyed.

    Use with caution! This operation is irreversible.

    Examples:

      mngr destroy my-agent

      mngr destroy agent1 agent2 agent3

      mngr destroy --agent my-agent --agent another-agent

      mngr destroy --session mngr-my-agent

      mngr destroy --all --force
    """
    # Setup command context (config, logging, output options)
    # This loads the config, applies defaults, and creates the final options
    mngr_ctx, output_opts, opts = setup_command_context(
        ctx=ctx,
        command_name="destroy",
        command_class=DestroyCliOptions,
    )

    # Filter agents to destroy using CEL expressions like:
    # --include 'name.startsWith("test-")' or --include 'host.provider == "docker"'
    # See mngr list --include for the pattern to follow
    if opts.include:
        raise NotImplementedError(
            "The --include option is not yet implemented. "
            "See https://github.com/imbue-ai/mngr/issues/XXX for progress."
        )
    # Exclude agents matching CEL expressions from destruction:
    # --exclude 'state == "RUNNING"' to skip running agents
    # See mngr list --exclude for the pattern to follow
    if opts.exclude:
        raise NotImplementedError(
            "The --exclude option is not yet implemented. "
            "See https://github.com/imbue-ai/mngr/issues/XXX for progress."
        )
    # Read agent names/IDs from stdin to allow piping agent lists:
    # mngr list --format jsonl | jq -r .name | mngr destroy --stdin
    if opts.stdin:
        raise NotImplementedError(
            "The --stdin option is not yet implemented. See https://github.com/imbue-ai/mngr/issues/XXX for progress."
        )

    # Validate input
    agent_identifiers = list(opts.agents) + list(opts.agent_list)

    # Handle --session option by extracting agent names from session names
    if opts.sessions:
        if agent_identifiers or opts.destroy_all:
            raise UserInputError("Cannot specify --session with agent names or --all")
        for session_name in opts.sessions:
            agent_name = get_agent_name_from_session(session_name, mngr_ctx.config.prefix)
            if agent_name is None:
                raise UserInputError(
                    f"Session '{session_name}' does not match the expected format. "
                    f"Session names should start with the configured prefix '{mngr_ctx.config.prefix}'."
                )
            agent_identifiers.append(agent_name)

    if not agent_identifiers and not opts.destroy_all:
        raise UserInputError("Must specify at least one agent or use --all")

    if agent_identifiers and opts.destroy_all:
        raise UserInputError("Cannot specify both agent names and --all")

    # Find agents to destroy
    try:
        targets = _find_agents_to_destroy(
            agent_identifiers=agent_identifiers,
            destroy_all=opts.destroy_all,
            mngr_ctx=mngr_ctx,
        )
    except AgentNotFoundError as e:
        if opts.force:
            targets = DestroyTargets(online_agents=[], offline_hosts=[])
            _output(f"Error destroying agent(s): {e}", output_opts)
        else:
            raise

    if not targets.online_agents and not targets.offline_hosts:
        _output("No agents found to destroy", output_opts)
        return

    # Handle dry-run mode
    if opts.dry_run:
        _output_targets(targets, "Would destroy:", output_opts)
        return

    # Confirm destruction if not forced
    if not opts.force:
        _confirm_destruction(targets)

    # Destroy agents on online hosts
    destroyed_agents: list[AgentName] = []
    for agent, host in targets.online_agents:
        try:
            if agent.is_running() and not opts.force:
                _output(
                    f"Agent {agent.name} is running. Use --force to destroy running agents.",
                    output_opts,
                )
                continue

            host.destroy_agent(agent)
            destroyed_agents.append(agent.name)
            _output(f"Destroyed agent: {agent.name}", output_opts)

        except MngrError as e:
            _output(f"Error destroying agent {agent.name}: {e}", output_opts)

    # Destroy offline hosts (which destroys all their agents)
    for offline in targets.offline_hosts:
        try:
            _output(f"Destroying offline host with {len(offline.agent_names)} agent(s)...", output_opts)
            offline.provider.destroy_host(offline.host, delete_snapshots=True)
            destroyed_agents.extend(offline.agent_names)
            for name in offline.agent_names:
                _output(f"Destroyed agent: {name} (via host destruction)", output_opts)
        except MngrError as e:
            _output(f"Error destroying offline host: {e}", output_opts)

    # Run garbage collection if enabled
    if opts.gc and not opts.dry_run and destroyed_agents:
        _run_post_destroy_gc(mngr_ctx=mngr_ctx, output_opts=output_opts)

    # Output final result
    _output_result(destroyed_agents, output_opts)


def _find_agents_to_destroy(
    agent_identifiers: list[str],
    destroy_all: bool,
    mngr_ctx: MngrContext,
) -> DestroyTargets:
    """Find all agents to destroy.

    Returns DestroyTargets containing online agents and offline hosts to destroy.
    Raises AgentNotFoundError if any specified identifier does not match an agent.
    """
    online_agents: list[tuple[AgentInterface, OnlineHostInterface]] = []
    offline_hosts: list[OfflineHostToDestroy] = []
    matched_identifiers: set[str] = set()
    seen_offline_hosts: set[str] = set()

    for agent_ref in list_agents(mngr_ctx, is_streaming=False).agents:
        should_include: bool
        if destroy_all:
            should_include = True
        elif agent_identifiers:
            agent_name_str = str(agent_ref.name)
            agent_id_str = str(agent_ref.id)

            should_include = False
            for identifier in agent_identifiers:
                if identifier == agent_name_str or identifier == agent_id_str:
                    should_include = True
                    matched_identifiers.add(identifier)
        else:
            should_include = False

        if should_include:
            provider = get_provider_instance(agent_ref.host.provider_name, mngr_ctx)
            host_interface = provider.get_host(agent_ref.host.id)

            match host_interface:
                case OnlineHostInterface() as online_host:
                    for agent in online_host.get_agents():
                        if agent.id == agent_ref.id:
                            online_agents.append((agent, online_host))
                            break
                    else:
                        raise AgentNotFoundError(f"Agent with ID {agent_ref.id} not found on host {online_host.id}")
                case HostInterface() as offline_host:
                    host_id_str = str(agent_ref.host.id)
                    if host_id_str in seen_offline_hosts:
                        continue

                    # Offline host - check if ALL agents on this host are being destroyed
                    all_agent_refs = offline_host.get_agent_references()
                    all_targeted = destroy_all or all(
                        str(ref.agent_name) in agent_identifiers or str(ref.agent_id) in agent_identifiers
                        for ref in all_agent_refs
                    )
                    if all_targeted:
                        # Collect the host for destruction (don't destroy yet)
                        offline_hosts.append(
                            OfflineHostToDestroy(
                                host=offline_host,
                                provider=provider,
                                agent_names=[ref.agent_name for ref in all_agent_refs],
                            )
                        )
                        seen_offline_hosts.add(host_id_str)
                        for ref in all_agent_refs:
                            matched_identifiers.add(str(ref.agent_name))
                            matched_identifiers.add(str(ref.agent_id))
                    else:
                        raise HostOfflineError(
                            f"Host '{agent_ref.host.id}' is offline. Cannot destroy individual agents on an offline host. "
                            f"Either start the host first, or destroy all {len(all_agent_refs)} agent(s) on this host."
                        )
                case _ as unreachable:
                    assert_never(unreachable)

    # Verify all specified identifiers were found
    if agent_identifiers:
        unmatched_identifiers = set(agent_identifiers) - matched_identifiers
        if unmatched_identifiers:
            unmatched_list = ", ".join(sorted(unmatched_identifiers))
            raise AgentNotFoundError(f"No agent(s) found matching: {unmatched_list}")

    return DestroyTargets(online_agents=online_agents, offline_hosts=offline_hosts)


def _confirm_destruction(targets: DestroyTargets) -> None:
    """Prompt user to confirm destruction of agents."""
    logger.info("\nThe following agents will be destroyed:")
    for agent, _ in targets.online_agents:
        logger.info("  - {}", agent.name)
    for offline in targets.offline_hosts:
        for name in offline.agent_names:
            logger.info("  - {} (on offline host)", name)

    logger.info("\nThis action is irreversible!")

    if not click.confirm("Are you sure you want to continue?"):
        raise click.Abort()


def _output_targets(
    targets: DestroyTargets,
    prefix: str,
    output_opts: OutputOptions,
) -> None:
    """Output a list of agents to destroy."""
    agent_data = [
        {"agent_id": str(agent.id), "agent_name": str(agent.name), "host_id": str(host.id)}
        for agent, host in targets.online_agents
    ]
    for offline in targets.offline_hosts:
        for name in offline.agent_names:
            agent_data.append({"agent_name": str(name), "host_id": str(offline.host.id), "host_offline": True})

    match output_opts.output_format:
        case OutputFormat.JSON:
            emit_final_json({"agents": agent_data})
        case OutputFormat.JSONL:
            emit_event("agents_list", {"agents": agent_data}, OutputFormat.JSONL)
        case OutputFormat.HUMAN:
            logger.info("\n{}", prefix)
            for agent, host in targets.online_agents:
                logger.info("  - {} (on host {})", agent.name, host.id)
            for offline in targets.offline_hosts:
                for name in offline.agent_names:
                    logger.info("  - {} (on offline host {})", name, offline.host.id)
        case _ as unreachable:
            assert_never(unreachable)


def _output(message: str, output_opts: OutputOptions) -> None:
    """Output a message according to the format."""
    if output_opts.output_format == OutputFormat.HUMAN:
        logger.info(message)


def _output_result(destroyed_agents: list[AgentName], output_opts: OutputOptions) -> None:
    """Output the final result."""
    result_data = {"destroyed_agents": [str(n) for n in destroyed_agents], "count": len(destroyed_agents)}
    match output_opts.output_format:
        case OutputFormat.JSON:
            emit_final_json(result_data)
        case OutputFormat.JSONL:
            emit_event("destroy_result", result_data, OutputFormat.JSONL)
        case OutputFormat.HUMAN:
            if destroyed_agents:
                logger.info("\nSuccessfully destroyed {} agent(s)", len(destroyed_agents))
        case _ as unreachable:
            assert_never(unreachable)


def _run_post_destroy_gc(mngr_ctx: MngrContext, output_opts: OutputOptions) -> None:
    """Run garbage collection after destroying agents.

    This cleans up orphaned host-level resources (machines, work dirs, snapshots, volumes).
    Errors are logged but don't prevent destroy from reporting success.
    """
    try:
        _output("Garbage collecting...", output_opts)

        providers = get_all_provider_instances(mngr_ctx)

        resource_types = GcResourceTypes(
            is_machines=True,
            is_work_dirs=True,
            is_snapshots=True,
            is_volumes=True,
            is_logs=False,
            is_build_cache=False,
        )

        result = api_gc(
            mngr_ctx=mngr_ctx,
            providers=providers,
            resource_types=resource_types,
            include_filters=(),
            exclude_filters=(),
            dry_run=False,
            error_behavior=ErrorBehavior.CONTINUE,
        )

        _output("Garbage collecting... done.", output_opts)

        if result.errors:
            logger.warning("Garbage collection completed with {} error(s)", len(result.errors))
            for error in result.errors:
                logger.warning("  - {}", error)

    except MngrError as e:
        logger.warning("Garbage collection failed: {}", e)
        logger.warning("This does not affect the destroy operation, which completed successfully")


# Register help metadata for git-style help formatting
_DESTROY_HELP_METADATA = CommandHelpMetadata(
    name="mngr-destroy",
    one_line_description="Destroy agent(s) and clean up resources",
    synopsis="mngr [destroy|rm] [AGENTS...] [--agent <AGENT>] [--all] [--session <SESSION>] [-f|--force] [--dry-run]",
    description="""Destroy one or more agents and clean up their resources.

When the last agent on a host is destroyed, the host itself is also destroyed
(including containers, volumes, snapshots, and any remote infrastructure).

Use with caution! This operation is irreversible.

By default, running agents cannot be destroyed. Use --force to stop and destroy
running agents. The command will prompt for confirmation before destroying
agents unless --force is specified.""",
    aliases=("rm",),
    examples=(
        ("Destroy an agent by name", "mngr destroy my-agent"),
        ("Destroy multiple agents", "mngr destroy agent1 agent2 agent3"),
        ("Destroy all agents", "mngr destroy --all --force"),
        ("Preview what would be destroyed", "mngr destroy my-agent --dry-run"),
    ),
    see_also=(
        ("create", "Create a new agent"),
        ("list", "List existing agents"),
        ("gc", "Garbage collect orphaned resources"),
    ),
    additional_sections=(
        (
            "Related Documentation",
            """- [Resource Cleanup Options](../generic/resource_cleanup.md) - Control which associated resources are destroyed
- [Multi-target Options](../generic/multi_target.md) - Behavior when targeting multiple agents""",
        ),
    ),
)

register_help_metadata("destroy", _DESTROY_HELP_METADATA)
# Also register under alias for consistent help output
for alias in _DESTROY_HELP_METADATA.aliases:
    register_help_metadata(alias, _DESTROY_HELP_METADATA)

# Add pager-enabled help option to the destroy command
add_pager_help_option(destroy)
