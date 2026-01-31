from typing import Any
from typing import assert_never

import click
from click_option_group import optgroup
from loguru import logger

from imbue.mngr.api.list import list_agents
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
from imbue.mngr.interfaces.host import HostInterface
from imbue.mngr.interfaces.host import OnlineHostInterface
from imbue.mngr.primitives import AgentLifecycleState
from imbue.mngr.primitives import OutputFormat


class StopCliOptions(CommonCliOptions):
    """Options passed from the CLI to the stop command."""

    agents: tuple[str, ...]
    agent_list: tuple[str, ...]
    stop_all: bool
    dry_run: bool


def _find_agents_to_stop(
    agent_identifiers: list[str],
    stop_all: bool,
    mngr_ctx: MngrContext,
) -> list[tuple[str, str, str, str]]:
    """Find all agents to stop.

    Returns a list of (agent_id, agent_name, host_id, provider_name) tuples.
    Raises AgentNotFoundError if any specified identifier does not match an agent.
    """
    agents_to_stop: list[tuple[str, str, str, str]] = []
    matched_identifiers: set[str] = set()

    for agent_ref in list_agents(mngr_ctx).agents:
        should_include: bool
        if stop_all:
            # Only include running agents when using --all
            if agent_ref.lifecycle_state == AgentLifecycleState.RUNNING:
                should_include = True
            else:
                should_include = False
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
            agents_to_stop.append((
                str(agent_ref.id),
                str(agent_ref.name),
                str(agent_ref.host.id),
                str(agent_ref.host.provider_name),
            ))

    # Verify all specified identifiers were found
    if agent_identifiers:
        unmatched_identifiers = set(agent_identifiers) - matched_identifiers
        if unmatched_identifiers:
            unmatched_list = ", ".join(sorted(unmatched_identifiers))
            raise AgentNotFoundError(f"No agent(s) found matching: {unmatched_list}")

    return agents_to_stop


def _output(message: str, output_opts: OutputOptions) -> None:
    """Output a message according to the format."""
    if output_opts.output_format == OutputFormat.HUMAN:
        logger.info(message)


def _output_result(stopped_agents: list[str], output_opts: OutputOptions) -> None:
    """Output the final result."""
    result_data = {"stopped_agents": stopped_agents, "count": len(stopped_agents)}
    match output_opts.output_format:
        case OutputFormat.JSON:
            emit_final_json(result_data)
        case OutputFormat.JSONL:
            emit_event("stop_result", result_data, OutputFormat.JSONL)
        case OutputFormat.HUMAN:
            if stopped_agents:
                logger.info("Successfully stopped {} agent(s)", len(stopped_agents))
        case _ as unreachable:
            assert_never(unreachable)


@click.command(name="stop")
@click.argument("agents", nargs=-1, required=False)
@optgroup.group("Target Selection")
@optgroup.option(
    "--agent",
    "agent_list",
    multiple=True,
    help="Agent name or ID to stop (can be specified multiple times)",
)
@optgroup.option(
    "-a",
    "--all",
    "--all-agents",
    "stop_all",
    is_flag=True,
    help="Stop all running agents",
)
@optgroup.group("Behavior")
@optgroup.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be stopped without actually stopping",
)
@add_common_options
@click.pass_context
def stop(ctx: click.Context, **kwargs: Any) -> None:
    """Stop running agent(s).

    For remote hosts, this stops the agent's tmux session. The host remains
    running (use idle detection or explicit host stop for host shutdown).

    For local agents, this stops the agent's tmux session.

    \b
    Alias: s

    Examples:

      mngr stop my-agent

      mngr stop agent1 agent2

      mngr stop --agent my-agent

      mngr stop --all
    """
    mngr_ctx, output_opts, opts = setup_command_context(
        ctx=ctx,
        command_name="stop",
        command_class=StopCliOptions,
    )
    logger.debug("Running stop command")

    # Validate input
    agent_identifiers = list(opts.agents) + list(opts.agent_list)

    if not agent_identifiers and not opts.stop_all:
        raise click.UsageError("Must specify at least one agent or use --all")

    if agent_identifiers and opts.stop_all:
        raise click.UsageError("Cannot specify both agent names and --all")

    # Find agents to stop
    agents_to_stop = _find_agents_to_stop(
        agent_identifiers=agent_identifiers,
        stop_all=opts.stop_all,
        mngr_ctx=mngr_ctx,
    )

    if not agents_to_stop:
        _output("No running agents found to stop", output_opts)
        return

    # Handle dry-run mode
    if opts.dry_run:
        _output("Would stop:", output_opts)
        for _agent_id, agent_name, host_id, _provider_name in agents_to_stop:
            _output(f"  - {agent_name} (on host {host_id})", output_opts)
        return

    # Stop each agent
    stopped_agents: list[str] = []

    # Group agents by host to stop them together
    agents_by_host: dict[str, list[tuple[str, str, str]]] = {}
    for agent_id, agent_name, host_id, provider_name in agents_to_stop:
        key = f"{host_id}:{provider_name}"
        if key not in agents_by_host:
            agents_by_host[key] = []
        agents_by_host[key].append((agent_id, agent_name, provider_name))

    from imbue.mngr.primitives import AgentId
    from imbue.mngr.primitives import HostId
    from imbue.mngr.primitives import ProviderInstanceName

    for host_key, agent_list in agents_by_host.items():
        host_id_str, _ = host_key.split(":", 1)
        # Get provider from first agent (all agents in list have same provider)
        _, _, provider_name = agent_list[0]

        try:
            provider = get_provider_instance(ProviderInstanceName(provider_name), mngr_ctx)
            host = provider.get_host(HostId(host_id_str))

            # Ensure host is online (can't stop agents on offline hosts)
            match host:
                case OnlineHostInterface() as online_host:
                    # Stop each agent on this host
                    agent_ids_to_stop = [AgentId(agent_id) for agent_id, _, _ in agent_list]
                    online_host.stop_agents(agent_ids_to_stop)

                    for _agent_id, agent_name, _ in agent_list:
                        stopped_agents.append(agent_name)
                        _output(f"Stopped agent: {agent_name}", output_opts)
                case HostInterface():
                    raise HostOfflineError(f"Host '{host_id_str}' is offline. Cannot stop agents on offline hosts.")
                case _ as unreachable:
                    assert_never(unreachable)

        except MngrError as e:
            agent_names = ", ".join(name for _, name, _ in agent_list)
            _output(f"Error stopping agent(s) {agent_names}: {e}", output_opts)

    # Output final result
    _output_result(stopped_agents, output_opts)


# Register help metadata for git-style help formatting
_STOP_HELP_METADATA = CommandHelpMetadata(
    name="mngr-stop",
    one_line_description="Stop running agent(s)",
    synopsis="mngr [stop|s] [AGENTS...] [--agent <AGENT>] [--all] [--dry-run]",
    description="""Stop one or more running agents.

For remote hosts, this stops the agent's tmux session. The host remains
running unless idle detection stops it automatically.

For local agents, this stops the agent's tmux session. The local host
itself cannot be stopped (if you want that, shut down your computer).""",
    aliases=("s",),
    examples=(
        ("Stop an agent by name", "mngr stop my-agent"),
        ("Stop multiple agents", "mngr stop agent1 agent2"),
        ("Stop all running agents", "mngr stop --all"),
        ("Preview what would be stopped", "mngr stop --all --dry-run"),
    ),
    see_also=(
        ("start", "Start stopped agents"),
        ("connect", "Connect to an agent"),
        ("list", "List existing agents"),
    ),
)

register_help_metadata("stop", _STOP_HELP_METADATA)
# Also register under alias for consistent help output
for alias in _STOP_HELP_METADATA.aliases:
    register_help_metadata(alias, _STOP_HELP_METADATA)

# Add pager-enabled help option to the stop command
add_pager_help_option(stop)
