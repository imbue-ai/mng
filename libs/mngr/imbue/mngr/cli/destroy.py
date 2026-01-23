from typing import assert_never

import click
from click_option_group import optgroup
from loguru import logger

from imbue.mngr.api.data_types import GcResourceTypes
from imbue.mngr.api.gc import gc as api_gc
from imbue.mngr.api.providers import get_all_provider_instances
from imbue.mngr.cli.common_opts import CommonCliOptions
from imbue.mngr.cli.common_opts import add_common_options
from imbue.mngr.cli.common_opts import setup_command_context
from imbue.mngr.cli.output_helpers import emit_event
from imbue.mngr.cli.output_helpers import emit_final_json
from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.config.data_types import OutputOptions
from imbue.mngr.errors import AgentNotFoundError
from imbue.mngr.errors import MngrError
from imbue.mngr.errors import UserInputError
from imbue.mngr.interfaces.agent import AgentInterface
from imbue.mngr.interfaces.host import HostInterface
from imbue.mngr.primitives import ErrorBehavior
from imbue.mngr.primitives import OutputFormat


def _get_agent_name_from_session(session_name: str, prefix: str) -> str | None:
    """Extract the agent name from a tmux session name.

    The session name is expected to be in the format "{prefix}{agent_name}".
    Returns the agent name if the session matches the prefix, or None if the
    session name doesn't match the expected prefix format.
    """
    if not session_name:
        logger.debug("Empty session name provided")
        return None

    # Check if the session name starts with our prefix
    if not session_name.startswith(prefix):
        logger.debug(
            "Session name '{}' doesn't start with mngr prefix '{}'",
            session_name,
            prefix,
        )
        return None

    # Extract the agent name by removing the prefix
    agent_name = session_name[len(prefix) :]
    if not agent_name:
        logger.debug("Session name '{}' has empty agent name after stripping prefix", session_name)
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
    logger.debug("Running destroy command")

    # Validate input
    agent_identifiers = list(opts.agents) + list(opts.agent_list)

    # Handle --session option by extracting agent names from session names
    if opts.sessions:
        if agent_identifiers or opts.destroy_all:
            raise UserInputError("Cannot specify --session with agent names or --all")
        for session_name in opts.sessions:
            agent_name = _get_agent_name_from_session(session_name, mngr_ctx.config.prefix)
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
    agents_to_destroy = _find_agents_to_destroy(
        agent_identifiers=agent_identifiers,
        destroy_all=opts.destroy_all,
        mngr_ctx=mngr_ctx,
    )

    if not agents_to_destroy:
        _output("No agents found to destroy", output_opts)
        return

    # Handle dry-run mode
    if opts.dry_run:
        _output_agents_list(agents_to_destroy, "Would destroy:", output_opts)
        return

    # Confirm destruction if not forced
    if not opts.force:
        _confirm_destruction(agents_to_destroy)

    # Destroy each agent
    destroyed_agents = []
    for agent, host in agents_to_destroy:
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

    # Run garbage collection if enabled
    if opts.gc and not opts.dry_run and destroyed_agents:
        _run_post_destroy_gc(mngr_ctx=mngr_ctx, output_opts=output_opts)

    # Output final result
    _output_result(destroyed_agents, output_opts)


def _find_agents_to_destroy(
    agent_identifiers: list[str],
    destroy_all: bool,
    mngr_ctx: MngrContext,
) -> list[tuple[AgentInterface, HostInterface]]:
    """Find all agents to destroy.

    Returns a list of (agent, host) tuples.
    Raises AgentNotFoundError if any specified identifier does not match an agent.
    """
    agents_to_destroy: list[tuple[AgentInterface, HostInterface]] = []
    matched_identifiers: set[str] = set()

    providers = get_all_provider_instances(mngr_ctx)

    for provider_instance in providers:
        for host in provider_instance.list_hosts():
            for agent in host.get_agents():
                should_include: bool
                if destroy_all:
                    should_include = True
                elif agent_identifiers:
                    agent_name_str = str(agent.name)
                    agent_id_str = str(agent.id)

                    should_include = False
                    for identifier in agent_identifiers:
                        if identifier == agent_name_str or identifier == agent_id_str:
                            should_include = True
                            matched_identifiers.add(identifier)
                else:
                    should_include = False

                if should_include:
                    agents_to_destroy.append((agent, host))

    # Verify all specified identifiers were found
    if agent_identifiers:
        unmatched_identifiers = set(agent_identifiers) - matched_identifiers
        if unmatched_identifiers:
            unmatched_list = ", ".join(sorted(unmatched_identifiers))
            raise AgentNotFoundError(f"No agent(s) found matching: {unmatched_list}")

    return agents_to_destroy


def _confirm_destruction(agents: list[tuple[AgentInterface, HostInterface]]) -> None:
    """Prompt user to confirm destruction of agents."""
    agent_names = [agent.name for agent, _ in agents]

    logger.info("\nThe following agents will be destroyed:")
    for name in agent_names:
        logger.info("  - {}", name)

    logger.info("\nThis action is irreversible!")

    if not click.confirm("Are you sure you want to continue?"):
        raise click.Abort()


def _output_agents_list(
    agents: list[tuple[AgentInterface, HostInterface]],
    prefix: str,
    output_opts: OutputOptions,
) -> None:
    """Output a list of agents."""
    agent_data = [
        {"agent_id": str(agent.id), "agent_name": str(agent.name), "host_id": str(host.id)} for agent, host in agents
    ]
    match output_opts.output_format:
        case OutputFormat.JSON:
            emit_final_json({"agents": agent_data})
        case OutputFormat.JSONL:
            emit_event("agents_list", {"agents": agent_data}, OutputFormat.JSONL)
        case OutputFormat.HUMAN:
            logger.info("\n{}", prefix)
            for agent, host in agents:
                logger.info("  - {} (on host {})", agent.name, host.id)
        case _ as unreachable:
            assert_never(unreachable)


def _output(message: str, output_opts: OutputOptions) -> None:
    """Output a message according to the format."""
    if output_opts.output_format == OutputFormat.HUMAN:
        logger.info(message)


def _output_result(destroyed_agents: list[str], output_opts: OutputOptions) -> None:
    """Output the final result."""
    result_data = {"destroyed_agents": destroyed_agents, "count": len(destroyed_agents)}
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
                logger.debug("  - {}", error)

    except MngrError as e:
        logger.warning("Garbage collection failed: {}", e)
        logger.debug("This does not affect the destroy operation, which completed successfully")
