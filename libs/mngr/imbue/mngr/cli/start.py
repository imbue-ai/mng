import time
from typing import Any
from typing import assert_never

import click
from click_option_group import optgroup
from loguru import logger

from imbue.mngr.api.connect import connect_to_agent
from imbue.mngr.api.data_types import ConnectionOptions
from imbue.mngr.api.find import ensure_host_started
from imbue.mngr.api.find import find_agents_by_identifiers_or_state
from imbue.mngr.api.find import group_agents_by_host
from imbue.mngr.api.providers import get_provider_instance
from imbue.mngr.cli.common_opts import CommonCliOptions
from imbue.mngr.cli.common_opts import add_common_options
from imbue.mngr.cli.common_opts import setup_command_context
from imbue.mngr.cli.help_formatter import CommandHelpMetadata
from imbue.mngr.cli.help_formatter import add_pager_help_option
from imbue.mngr.cli.help_formatter import register_help_metadata
from imbue.mngr.cli.output_helpers import emit_event
from imbue.mngr.cli.output_helpers import emit_final_json
from imbue.mngr.config.data_types import OutputOptions
from imbue.mngr.interfaces.agent import AgentInterface
from imbue.mngr.primitives import AgentLifecycleState
from imbue.mngr.primitives import HostId
from imbue.mngr.primitives import OutputFormat


class StartCliOptions(CommonCliOptions):
    """Options passed from the CLI to the start command."""

    agents: tuple[str, ...]
    agent_list: tuple[str, ...]
    start_all: bool
    dry_run: bool
    connect: bool


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


def _send_resume_message_if_configured(agent: AgentInterface, output_opts: OutputOptions) -> None:
    """Send the resume message to an agent if one is configured."""
    resume_message = agent.get_resume_message()
    if resume_message is None:
        return

    message_delay = agent.get_message_delay_seconds()
    _output(f"Sending resume message to {agent.name}...", output_opts)
    logger.debug("Waiting {}s before sending resume message", message_delay)
    time.sleep(message_delay)
    agent.send_message(resume_message)
    logger.debug("Resume message sent to agent {}", agent.name)


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

    # Find agents to start (STOPPED agents when using --all)
    agents_to_start = find_agents_by_identifiers_or_state(
        agent_identifiers=agent_identifiers,
        filter_all=opts.start_all,
        target_state=AgentLifecycleState.STOPPED,
        mngr_ctx=mngr_ctx,
    )

    if not agents_to_start:
        _output("No stopped agents found to start", output_opts)
        return

    # Handle dry-run mode
    if opts.dry_run:
        _output("Would start:", output_opts)
        for match in agents_to_start:
            _output(f"  - {match.agent_name} (on host {match.host_id})", output_opts)
        return

    # Start each agent
    started_agents: list[str] = []
    last_started_agent = None
    last_started_host = None

    # Group agents by host to avoid starting the same host multiple times
    agents_by_host = group_agents_by_host(agents_to_start)

    for host_key, agent_list in agents_by_host.items():
        host_id_str, _ = host_key.split(":", 1)
        # Get provider from first agent (all agents in list have same provider)
        provider_name = agent_list[0].provider_name

        provider = get_provider_instance(provider_name, mngr_ctx)
        host = provider.get_host(HostId(host_id_str))

        # Ensure host is started (always start since this is the start command)
        online_host = ensure_host_started(host, is_start_desired=True, provider=provider)

        # Start each agent on this host
        agent_ids_to_start = [match.agent_id for match in agent_list]
        online_host.start_agents(agent_ids_to_start)

        for match in agent_list:
            started_agents.append(str(match.agent_name))
            _output(f"Started agent: {match.agent_name}", output_opts)

            # Get the agent object for potential connect and resume message
            for agent in online_host.get_agents():
                if agent.id == match.agent_id:
                    # Send resume message if configured
                    _send_resume_message_if_configured(agent, output_opts)

                    # Track for potential connect
                    if opts.connect:
                        last_started_agent = agent
                        last_started_host = online_host
                    break

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
