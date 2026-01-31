from typing import Any
from typing import assert_never

import click
from click_option_group import optgroup
from loguru import logger

from imbue.mngr.api.connect import connect_to_agent
from imbue.mngr.api.data_types import ConnectionOptions
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
from imbue.mngr.errors import MngrError
from imbue.mngr.hosts.host import Host
from imbue.mngr.interfaces.host import HostInterface
from imbue.mngr.interfaces.host import OnlineHostInterface
from imbue.mngr.primitives import AgentId
from imbue.mngr.primitives import AgentLifecycleState
from imbue.mngr.primitives import HostId
from imbue.mngr.primitives import OutputFormat
from imbue.mngr.primitives import ProviderInstanceName
from imbue.mngr.providers.base_provider import BaseProviderInstance


class StartCliOptions(CommonCliOptions):
    """Options passed from the CLI to the start command."""

    agents: tuple[str, ...]
    agent_list: tuple[str, ...]
    start_all: bool
    dry_run: bool
    connect: bool


def _ensure_host_started(host: HostInterface, provider: BaseProviderInstance) -> OnlineHostInterface:
    """Ensure the host is online and started."""
    match host:
        case Host() as online_host:
            return online_host
        case HostInterface() as offline_host:
            logger.info("Host is offline, starting it...")
            started_host = provider.start_host(offline_host)
            return started_host
        case _ as unreachable:
            assert_never(unreachable)


def _find_agents_to_start(
    agent_identifiers: list[str],
    start_all: bool,
    mngr_ctx: MngrContext,
) -> list[tuple[str, str, str, str]]:
    """Find all agents to start.

    Returns a list of (agent_id, agent_name, host_id, provider_name) tuples.
    Raises AgentNotFoundError if any specified identifier does not match an agent.
    """
    agents_to_start: list[tuple[str, str, str, str]] = []
    matched_identifiers: set[str] = set()

    for agent_ref in list_agents(mngr_ctx).agents:
        should_include: bool
        if start_all:
            # Only include stopped agents when using --all
            if agent_ref.lifecycle_state == AgentLifecycleState.STOPPED:
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
            agents_to_start.append((
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

    return agents_to_start


def _output(message: str, output_opts: OutputOptions) -> None:
    """Output a message according to the format."""
    if output_opts.output_format == OutputFormat.HUMAN:
        logger.info(message)


def _output_result(started_agents: list[str], output_opts: OutputOptions) -> None:
    """Output the final result."""
    result_data = {"started_agents": started_agents, "count": len(started_agents)}
    match output_opts.output_format:
        case OutputFormat.JSON:
            emit_final_json(result_data)
        case OutputFormat.JSONL:
            emit_event("start_result", result_data, OutputFormat.JSONL)
        case OutputFormat.HUMAN:
            if started_agents:
                logger.info("Successfully started {} agent(s)", len(started_agents))
        case _ as unreachable:
            assert_never(unreachable)


@click.command(name="start")
@click.argument("agents", nargs=-1, required=False)
@optgroup.group("Target Selection")
@optgroup.option(
    "--agent",
    "agent_list",
    multiple=True,
    help="Agent name or ID to start (can be specified multiple times)",
)
@optgroup.option(
    "-a",
    "--all",
    "--all-agents",
    "start_all",
    is_flag=True,
    help="Start all stopped agents",
)
@optgroup.group("Behavior")
@optgroup.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be started without actually starting",
)
@optgroup.option(
    "--connect/--no-connect",
    default=False,
    help="Connect to the agent after starting (only valid for single agent)",
)
@add_common_options
@click.pass_context
def start(ctx: click.Context, **kwargs: Any) -> None:
    """Start stopped agent(s).

    For remote hosts, this restores from the most recent snapshot and starts
    the container/instance. For local agents, this starts the agent's tmux
    session.

    Examples:

      mngr start my-agent

      mngr start agent1 agent2

      mngr start --agent my-agent --connect

      mngr start --all
    """
    mngr_ctx, output_opts, opts = setup_command_context(
        ctx=ctx,
        command_name="start",
        command_class=StartCliOptions,
    )
    logger.debug("Running start command")

    # Validate input
    agent_identifiers = list(opts.agents) + list(opts.agent_list)

    if not agent_identifiers and not opts.start_all:
        raise click.UsageError("Must specify at least one agent or use --all")

    if agent_identifiers and opts.start_all:
        raise click.UsageError("Cannot specify both agent names and --all")

    if opts.connect and (opts.start_all or len(agent_identifiers) > 1):
        raise click.UsageError("--connect can only be used with a single agent")

    # Find agents to start
    agents_to_start = _find_agents_to_start(
        agent_identifiers=agent_identifiers,
        start_all=opts.start_all,
        mngr_ctx=mngr_ctx,
    )

    if not agents_to_start:
        _output("No stopped agents found to start", output_opts)
        return

    # Handle dry-run mode
    if opts.dry_run:
        _output("Would start:", output_opts)
        for _agent_id, agent_name, host_id, _provider_name in agents_to_start:
            _output(f"  - {agent_name} (on host {host_id})", output_opts)
        return

    # Start each agent
    started_agents: list[str] = []
    last_started_agent = None
    last_started_host = None

    # Group agents by host to avoid starting the same host multiple times
    agents_by_host: dict[str, list[tuple[str, str, str]]] = {}
    for agent_id, agent_name, host_id, provider_name in agents_to_start:
        key = f"{host_id}:{provider_name}"
        if key not in agents_by_host:
            agents_by_host[key] = []
        agents_by_host[key].append((agent_id, agent_name, provider_name))

    for host_key, agent_list in agents_by_host.items():
        host_id_str, _ = host_key.split(":", 1)
        # Get provider from first agent (all agents in list have same provider)
        _, _, provider_name = agent_list[0]

        try:
            provider = get_provider_instance(ProviderInstanceName(provider_name), mngr_ctx)
            host = provider.get_host(HostId(host_id_str))

            # Ensure host is started
            online_host = _ensure_host_started(host, provider)

            # Start each agent on this host
            agent_ids_to_start = [AgentId(agent_id) for agent_id, _, _ in agent_list]
            online_host.start_agents(agent_ids_to_start)

            for agent_id, agent_name, _ in agent_list:
                started_agents.append(agent_name)
                _output(f"Started agent: {agent_name}", output_opts)

                # Track for potential connect
                if opts.connect:
                    for agent in online_host.get_agents():
                        if str(agent.id) == agent_id:
                            last_started_agent = agent
                            last_started_host = online_host
                            break

        except MngrError as e:
            agent_names = ", ".join(name for _, name, _ in agent_list)
            _output(f"Error starting agent(s) {agent_names}: {e}", output_opts)

    # Output final result
    _output_result(started_agents, output_opts)

    # Connect if requested and we started exactly one agent
    if opts.connect and last_started_agent is not None and last_started_host is not None:
        connection_opts = ConnectionOptions(
            is_reconnect=True,
            retry_count=3,
            retry_delay="5s",
            attach_command=None,
            is_unknown_host_allowed=False,
        )
        logger.info("Connecting to agent: {}", last_started_agent.name)
        connect_to_agent(last_started_agent, last_started_host, mngr_ctx, connection_opts)


# Register help metadata for git-style help formatting
_START_HELP_METADATA = CommandHelpMetadata(
    name="mngr-start",
    one_line_description="Start stopped agent(s)",
    synopsis="mngr start [AGENTS...] [--agent <AGENT>] [--all] [--connect] [--dry-run]",
    description="""Start one or more stopped agents.

For remote hosts, this restores from the most recent snapshot and starts
the container/instance. For local agents, this starts the agent's tmux
session.

If multiple agents share a host, they will all be started together when
the host starts.""",
    aliases=(),
    examples=(
        ("Start an agent by name", "mngr start my-agent"),
        ("Start multiple agents", "mngr start agent1 agent2"),
        ("Start and connect", "mngr start my-agent --connect"),
        ("Start all stopped agents", "mngr start --all"),
        ("Preview what would be started", "mngr start --all --dry-run"),
    ),
    see_also=(
        ("stop", "Stop running agents"),
        ("connect", "Connect to an agent"),
        ("list", "List existing agents"),
    ),
)

register_help_metadata("start", _START_HELP_METADATA)

# Add pager-enabled help option to the start command
add_pager_help_option(start)
