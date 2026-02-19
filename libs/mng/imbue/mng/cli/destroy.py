from collections.abc import Sequence
from typing import assert_never

import click
from click_option_group import optgroup
from loguru import logger
from pydantic import Field

from imbue.imbue_common.frozen_model import FrozenModel
from imbue.mng.api.data_types import GcResourceTypes
from imbue.mng.api.gc import gc as api_gc
from imbue.mng.api.list import load_all_agents_grouped_by_host
from imbue.mng.api.providers import get_all_provider_instances
from imbue.mng.api.providers import get_provider_instance
from imbue.mng.cli.common_opts import CommonCliOptions
from imbue.mng.cli.common_opts import add_common_options
from imbue.mng.cli.common_opts import setup_command_context
from imbue.mng.cli.completion import complete_agent_name
from imbue.mng.cli.help_formatter import CommandHelpMetadata
from imbue.mng.cli.help_formatter import add_pager_help_option
from imbue.mng.cli.help_formatter import register_help_metadata
from imbue.mng.cli.output_helpers import emit_event
from imbue.mng.cli.output_helpers import emit_final_json
from imbue.mng.cli.output_helpers import emit_format_template_lines
from imbue.mng.cli.output_helpers import write_human_line
from imbue.mng.config.data_types import MngContext
from imbue.mng.config.data_types import OutputOptions
from imbue.mng.errors import AgentNotFoundError
from imbue.mng.errors import HostOfflineError
from imbue.mng.errors import MngError
from imbue.mng.errors import UserInputError
from imbue.mng.interfaces.agent import AgentInterface
from imbue.mng.interfaces.host import HostInterface
from imbue.mng.interfaces.host import OnlineHostInterface
from imbue.mng.interfaces.provider_instance import ProviderInstanceInterface
from imbue.mng.primitives import AgentName
from imbue.mng.primitives import ErrorBehavior
from imbue.mng.primitives import OutputFormat


class _OfflineHostToDestroy(FrozenModel):
    """An offline host where all agents are targeted for destruction."""

    model_config = {**FrozenModel.model_config, "arbitrary_types_allowed": True}

    host: HostInterface = Field(description="The offline host to destroy")
    provider: ProviderInstanceInterface = Field(description="The provider instance for this host")
    agent_names: list[AgentName] = Field(description="Names of agents on this host targeted for destruction")


class _DestroyTargets(FrozenModel):
    """Result of finding agents/hosts to destroy."""

    model_config = {**FrozenModel.model_config, "arbitrary_types_allowed": True}

    online_agents: list[tuple[AgentInterface, OnlineHostInterface]] = Field(
        description="Agents on online hosts to destroy, paired with their host"
    )
    offline_hosts: list[_OfflineHostToDestroy] = Field(
        description="Offline hosts where all agents are targeted for destruction"
    )


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
            "Failed to extract agent name: session name '{}' doesn't start with mng prefix '{}'",
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
@click.argument("agents", nargs=-1, required=False, shell_complete=complete_agent_name)
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

    Supports custom format templates via --format. Available fields: name.

    Examples:

      mng destroy my-agent

      mng destroy agent1 agent2 agent3

      mng destroy --agent my-agent --agent another-agent

      mng destroy --session mng-my-agent

      mng destroy --all --force

      mng destroy --all --force --format '{name}'
    """
    # Setup command context (config, logging, output options)
    # This loads the config, applies defaults, and creates the final options
    mng_ctx, output_opts, opts = setup_command_context(
        ctx=ctx,
        command_name="destroy",
        command_class=DestroyCliOptions,
        is_format_template_supported=True,
    )

    # Filter agents to destroy using CEL expressions like:
    # --include 'name.startsWith("test-")' or --include 'host.provider == "docker"'
    # See mng list --include for the pattern to follow
    if opts.include:
        raise NotImplementedError(
            "The --include option is not yet implemented. "
            "See https://github.com/imbue-ai/mngr/issues/XXX for progress."
        )
    # Exclude agents matching CEL expressions from destruction:
    # --exclude 'state == "RUNNING"' to skip running agents
    # See mng list --exclude for the pattern to follow
    if opts.exclude:
        raise NotImplementedError(
            "The --exclude option is not yet implemented. "
            "See https://github.com/imbue-ai/mngr/issues/XXX for progress."
        )
    # Read agent names/IDs from stdin to allow piping agent lists:
    # mng list --format jsonl | jq -r .name | mng destroy --stdin
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
            agent_name = get_agent_name_from_session(session_name, mng_ctx.config.prefix)
            if agent_name is None:
                raise UserInputError(
                    f"Session '{session_name}' does not match the expected format. "
                    f"Session names should start with the configured prefix '{mng_ctx.config.prefix}'."
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
            mng_ctx=mng_ctx,
        )
    except AgentNotFoundError as e:
        if opts.force:
            targets = _DestroyTargets(online_agents=[], offline_hosts=[])
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

            mng_ctx.pm.hook.on_before_agent_destroy(agent=agent, host=host)
            host.destroy_agent(agent)
            mng_ctx.pm.hook.on_agent_destroyed(agent=agent, host=host)
            destroyed_agents.append(agent.name)
            _output(f"Destroyed agent: {agent.name}", output_opts)

        except MngError as e:
            _output(f"Error destroying agent {agent.name}: {e}", output_opts)

    # Destroy offline hosts (which destroys all their agents)
    for offline in targets.offline_hosts:
        try:
            _output(f"Destroying offline host with {len(offline.agent_names)} agent(s)...", output_opts)
            mng_ctx.pm.hook.on_before_host_destroy(host=offline.host)
            offline.provider.destroy_host(offline.host)
            mng_ctx.pm.hook.on_host_destroyed(host=offline.host)
            destroyed_agents.extend(offline.agent_names)
            for name in offline.agent_names:
                _output(f"Destroyed agent: {name} (via host destruction)", output_opts)
        except MngError as e:
            _output(f"Error destroying offline host: {e}", output_opts)

    # Run garbage collection if enabled
    if opts.gc and not opts.dry_run and destroyed_agents:
        _run_post_destroy_gc(mng_ctx=mng_ctx, output_opts=output_opts)

    # Output final result
    _output_result(destroyed_agents, output_opts)


def _find_agents_to_destroy(
    agent_identifiers: Sequence[str],
    destroy_all: bool,
    mng_ctx: MngContext,
) -> _DestroyTargets:
    """Find all agents to destroy.

    Returns _DestroyTargets containing online agents and offline hosts to destroy.
    Raises AgentNotFoundError if any specified identifier does not match an agent.
    """
    online_agents: list[tuple[AgentInterface, OnlineHostInterface]] = []
    offline_hosts: list[_OfflineHostToDestroy] = []
    matched_identifiers: set[str] = set()
    seen_offline_hosts: set[str] = set()

    agents_by_host, _ = load_all_agents_grouped_by_host(mng_ctx, include_destroyed=False)

    for host_ref, agent_refs in agents_by_host.items():
        for agent_ref in agent_refs:
            should_include: bool
            if destroy_all:
                should_include = True
            elif agent_identifiers:
                agent_name_str = str(agent_ref.agent_name)
                agent_id_str = str(agent_ref.agent_id)

                should_include = False
                for identifier in agent_identifiers:
                    if identifier == agent_name_str or identifier == agent_id_str:
                        should_include = True
                        matched_identifiers.add(identifier)
            else:
                should_include = False

            if should_include:
                provider = get_provider_instance(host_ref.provider_name, mng_ctx)
                host_interface = provider.get_host(host_ref.host_id)

                match host_interface:
                    case OnlineHostInterface() as online_host:
                        for agent in online_host.get_agents():
                            if agent.id == agent_ref.agent_id:
                                online_agents.append((agent, online_host))
                                break
                        else:
                            raise AgentNotFoundError(
                                f"Agent with ID {agent_ref.agent_id} not found on host {online_host.id}"
                            )
                    case HostInterface() as offline_host:
                        host_id_str = str(host_ref.host_id)
                        if host_id_str in seen_offline_hosts:
                            continue

                        # Offline host - check if ALL agents on this host are being destroyed
                        all_agent_refs_on_host = offline_host.get_agent_references()
                        all_targeted = destroy_all or all(
                            str(ref.agent_name) in agent_identifiers or str(ref.agent_id) in agent_identifiers
                            for ref in all_agent_refs_on_host
                        )
                        if all_targeted:
                            # Collect the host for destruction (don't destroy yet)
                            offline_hosts.append(
                                _OfflineHostToDestroy(
                                    host=offline_host,
                                    provider=provider,
                                    agent_names=[ref.agent_name for ref in all_agent_refs_on_host],
                                )
                            )
                            seen_offline_hosts.add(host_id_str)
                            for ref in all_agent_refs_on_host:
                                matched_identifiers.add(str(ref.agent_name))
                                matched_identifiers.add(str(ref.agent_id))
                        else:
                            raise HostOfflineError(
                                f"Host '{host_ref.host_id}' is offline. Cannot destroy individual agents on an "
                                f"offline host. Either start the host first, or destroy all "
                                f"{len(all_agent_refs_on_host)} agent(s) on this host."
                            )
                    case _ as unreachable:
                        assert_never(unreachable)

    # Verify all specified identifiers were found
    if agent_identifiers:
        unmatched_identifiers = set(agent_identifiers) - matched_identifiers
        if unmatched_identifiers:
            unmatched_list = ", ".join(sorted(unmatched_identifiers))
            raise AgentNotFoundError(f"No agent(s) found matching: {unmatched_list}")

    return _DestroyTargets(online_agents=online_agents, offline_hosts=offline_hosts)


def _confirm_destruction(targets: _DestroyTargets) -> None:
    """Prompt user to confirm destruction of agents."""
    write_human_line("\nThe following agents will be destroyed:")
    for agent, _ in targets.online_agents:
        write_human_line("  - {}", agent.name)
    for offline in targets.offline_hosts:
        for name in offline.agent_names:
            write_human_line("  - {} (on offline host)", name)

    write_human_line("\nThis action is irreversible!")

    if not click.confirm("Are you sure you want to continue?"):
        raise click.Abort()


def _output_targets(
    targets: _DestroyTargets,
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
            write_human_line("\n{}", prefix)
            for agent, host in targets.online_agents:
                write_human_line("  - {} (on host {})", agent.name, host.id)
            for offline in targets.offline_hosts:
                for name in offline.agent_names:
                    write_human_line("  - {} (on offline host {})", name, offline.host.id)
        case _ as unreachable:
            assert_never(unreachable)


def _output(message: str, output_opts: OutputOptions) -> None:
    """Output a message according to the format."""
    if output_opts.output_format == OutputFormat.HUMAN:
        write_human_line(message)


def _output_result(destroyed_agents: Sequence[AgentName], output_opts: OutputOptions) -> None:
    """Output the final result."""
    if output_opts.format_template is not None:
        items = [{"name": str(n)} for n in destroyed_agents]
        emit_format_template_lines(output_opts.format_template, items)
        return
    result_data = {"destroyed_agents": [str(n) for n in destroyed_agents], "count": len(destroyed_agents)}
    match output_opts.output_format:
        case OutputFormat.JSON:
            emit_final_json(result_data)
        case OutputFormat.JSONL:
            emit_event("destroy_result", result_data, OutputFormat.JSONL)
        case OutputFormat.HUMAN:
            if destroyed_agents:
                write_human_line("\nSuccessfully destroyed {} agent(s)", len(destroyed_agents))
        case _ as unreachable:
            assert_never(unreachable)


def _run_post_destroy_gc(mng_ctx: MngContext, output_opts: OutputOptions) -> None:
    """Run garbage collection after destroying agents.

    This cleans up orphaned host-level resources (machines, work dirs, snapshots, volumes).
    Errors are logged but don't prevent destroy from reporting success.
    """
    try:
        _output("Garbage collecting...", output_opts)

        providers = get_all_provider_instances(mng_ctx)

        resource_types = GcResourceTypes(
            is_machines=True,
            is_work_dirs=True,
            is_snapshots=True,
            is_volumes=True,
            is_logs=False,
            is_build_cache=False,
        )

        result = api_gc(
            mng_ctx=mng_ctx,
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

    except MngError as e:
        logger.warning("Garbage collection failed: {}", e)
        logger.warning("This does not affect the destroy operation, which completed successfully")


# Register help metadata for git-style help formatting
_DESTROY_HELP_METADATA = CommandHelpMetadata(
    name="mng-destroy",
    one_line_description="Destroy agent(s) and clean up resources",
    synopsis="mng [destroy|rm] [AGENTS...] [--agent <AGENT>] [--all] [--session <SESSION>] [-f|--force] [--dry-run]",
    description="""Destroy one or more agents and clean up their resources.

When the last agent on a host is destroyed, the host itself is also destroyed
(including containers, volumes, snapshots, and any remote infrastructure).

Use with caution! This operation is irreversible.

By default, running agents cannot be destroyed. Use --force to stop and destroy
running agents. The command will prompt for confirmation before destroying
agents unless --force is specified.""",
    aliases=("rm",),
    examples=(
        ("Destroy an agent by name", "mng destroy my-agent"),
        ("Destroy multiple agents", "mng destroy agent1 agent2 agent3"),
        ("Destroy all agents", "mng destroy --all --force"),
        ("Preview what would be destroyed", "mng destroy my-agent --dry-run"),
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
