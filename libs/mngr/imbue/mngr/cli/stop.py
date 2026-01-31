from typing import Any
from typing import assert_never

import click
from click_option_group import optgroup
from loguru import logger

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
from imbue.mngr.errors import HostOfflineError
from imbue.mngr.errors import MngrError
from imbue.mngr.interfaces.host import HostInterface
from imbue.mngr.interfaces.host import OnlineHostInterface
from imbue.mngr.primitives import AgentLifecycleState
from imbue.mngr.primitives import HostId
from imbue.mngr.primitives import OutputFormat


class StopCliOptions(CommonCliOptions):
    """Options passed from the CLI to the stop command."""

    agents: tuple[str, ...]
    agent_list: tuple[str, ...]
    stop_all: bool
    dry_run: bool


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

    # Find agents to stop (RUNNING agents when using --all)
    agents_to_stop = find_agents_by_identifiers_or_state(
        agent_identifiers=agent_identifiers,
        filter_all=opts.stop_all,
        target_state=AgentLifecycleState.RUNNING,
        mngr_ctx=mngr_ctx,
    )

    if not agents_to_stop:
        _output("No running agents found to stop", output_opts)
        return

    # Handle dry-run mode
    if opts.dry_run:
        _output("Would stop:", output_opts)
        for match in agents_to_stop:
            _output(f"  - {match.agent_name} (on host {match.host_id})", output_opts)
        return

    # Stop each agent
    stopped_agents: list[str] = []

    # Group agents by host to stop them together
    agents_by_host = group_agents_by_host(agents_to_stop)

    for host_key, agent_list in agents_by_host.items():
        host_id_str, _ = host_key.split(":", 1)
        # Get provider from first agent (all agents in list have same provider)
        provider_name = agent_list[0].provider_name

        try:
            provider = get_provider_instance(provider_name, mngr_ctx)
            host = provider.get_host(HostId(host_id_str))

            # Ensure host is online (can't stop agents on offline hosts)
            match host:
                case OnlineHostInterface() as online_host:
                    # Stop each agent on this host
                    agent_ids_to_stop = [m.agent_id for m in agent_list]
                    online_host.stop_agents(agent_ids_to_stop)

                    for m in agent_list:
                        stopped_agents.append(str(m.agent_name))
                        _output(f"Stopped agent: {m.agent_name}", output_opts)
                case HostInterface():
                    raise HostOfflineError(f"Host '{host_id_str}' is offline. Cannot stop agents on offline hosts.")
                case _ as unreachable:
                    assert_never(unreachable)

        except MngrError as e:
            agent_names = ", ".join(str(m.agent_name) for m in agent_list)
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
