import time
from typing import cast

from loguru import logger

from imbue.mngr.api.data_types import CreateAgentResult
from imbue.mngr.api.data_types import NewHostOptions
from imbue.mngr.api.data_types import OnBeforeCreateArgs
from imbue.mngr.api.providers import get_provider_instance
from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.hosts.host import HostLocation
from imbue.mngr.interfaces.agent import AgentInterface
from imbue.mngr.interfaces.host import CreateAgentOptions
from imbue.mngr.interfaces.host import OnlineHostInterface
from imbue.mngr.primitives import AgentLifecycleState
from imbue.mngr.utils.logging import log_call


def _wait_for_agent_ready(
    agent: AgentInterface,
    timeout_seconds: float,
    poll_interval_seconds: float = 0.2,
) -> bool:
    """Wait for the agent to reach WAITING state, indicating it's ready for input.

    Some agents (like Claude) configure hooks that create a 'waiting' file when
    they're ready to accept input. This function polls the agent's lifecycle state
    until it reaches WAITING, or until the timeout expires.

    Returns True if the agent reached WAITING state, False if timeout occurred.
    """
    start_time = time.monotonic()
    while time.monotonic() - start_time < timeout_seconds:
        state = agent.get_lifecycle_state()
        if state == AgentLifecycleState.WAITING:
            logger.debug("Agent {} reached WAITING state", agent.name)
            return True
        time.sleep(poll_interval_seconds)
    return False


def _call_on_before_create_hooks(
    mngr_ctx: MngrContext,
    target_host: OnlineHostInterface | NewHostOptions,
    agent_options: CreateAgentOptions,
    create_work_dir: bool,
) -> tuple[OnlineHostInterface | NewHostOptions, CreateAgentOptions, bool]:
    """Call on_before_create hooks in a chain, passing each hook's output to the next.

    Each hook receives an OnBeforeCreateArgs containing the current values.
    If a hook returns a new OnBeforeCreateArgs, those values are used for subsequent hooks.
    If a hook returns None, the current values are passed through unchanged.

    Returns the final (possibly modified) values as a tuple.
    """
    pm = mngr_ctx.pm

    # Bundle args into the hook's expected format
    current_args: OnBeforeCreateArgs = OnBeforeCreateArgs(
        target_host=target_host,
        agent_options=agent_options,
        create_work_dir=create_work_dir,
    )

    # Get all hook implementations and call them in order, chaining results
    hookimpls = pm.hook.on_before_create.get_hookimpls()
    for hookimpl in hookimpls:
        # Call the hook with current args
        result = cast(OnBeforeCreateArgs | None, hookimpl.function(args=current_args))
        # If the hook returned a new args object, use it for subsequent hooks
        if result is not None:
            current_args = result

    # Return the final values
    return current_args.target_host, current_args.agent_options, current_args.create_work_dir


@log_call
def create(
    source_location: HostLocation,
    target_host: OnlineHostInterface | NewHostOptions,
    agent_options: CreateAgentOptions,
    mngr_ctx: MngrContext,
    create_work_dir: bool = True,
) -> CreateAgentResult:
    """Create and run an agent.

    This function:
    - Resolves the target host (using existing or creating new)
    - Resolves the source location to concrete host and path
    - Sets up the agent's work_dir (cloning from source if specified)
    - Creates the agent state directory
    - Runs provisioning for the agent
    - Starts the agent process
    - Returns information about the running agent and host.
    """
    # Allow plugins to modify the create arguments before we do anything else
    target_host, agent_options, create_work_dir = _call_on_before_create_hooks(
        mngr_ctx, target_host, agent_options, create_work_dir
    )

    # Determine which provider to use and get the host
    logger.debug("Resolving target host")
    host = resolve_target_host(target_host, mngr_ctx)
    logger.trace("Resolved to host id={} name={}", host.id, host.connector.name)

    if create_work_dir:
        # Create the agent's work_dir on the host
        logger.debug("Creating agent work directory from source {}", source_location.path)
        work_dir_path = host.create_agent_work_dir(source_location.host, source_location.path, agent_options)
        logger.trace("Created work directory at {}", work_dir_path)
    else:
        work_dir_path = source_location.path

    # Create the agent state (registers the agent with the host)
    logger.debug("Creating agent state in work directory {}", work_dir_path)
    agent = host.create_agent_state(work_dir_path, agent_options)
    logger.trace("Created agent id={} name={} type={}", agent.id, agent.name, agent.agent_type)

    # Run provisioning for the agent (hooks, dependency installation, etc.)
    logger.debug("Provisioning agent {}", agent.name)
    host.provision_agent(agent, agent_options, mngr_ctx)

    # Start the agent
    logger.info("Starting agent {} ...", agent.name)
    host.start_agents([agent.id])

    # Send initial message if one is configured
    initial_message = agent.get_initial_message()
    if initial_message is not None:
        logger.info("Sending initial message...")
        # Wait for the agent to signal readiness via the WAITING lifecycle state.
        # Agents like Claude configure hooks that create a 'waiting' file when ready.
        # If the agent doesn't support this (no WAITING state within timeout),
        # fall back to a time-based delay.
        logger.debug("Waiting for agent to become ready before sending initial message")
        if _wait_for_agent_ready(agent, timeout_seconds=agent_options.message_delay_seconds):
            logger.debug("Agent signaled readiness via WAITING state")
        else:
            logger.debug(
                "Agent did not reach WAITING state within {}s, proceeding anyway",
                agent_options.message_delay_seconds,
            )
        agent.send_message(initial_message)

    # Build and return the result
    result = CreateAgentResult(agent=agent, host=host)

    # Call on_agent_created hooks to notify plugins about the new agent
    logger.debug("Calling on_agent_created hooks")
    mngr_ctx.pm.hook.on_agent_created(agent=result.agent, host=result.host)

    return result


def resolve_target_host(
    target_host: OnlineHostInterface | NewHostOptions,
    mngr_ctx: MngrContext,
) -> OnlineHostInterface:
    """Resolve which host to use for the agent."""
    if target_host is not None and isinstance(target_host, NewHostOptions):
        # Create a new host using the specified provider
        logger.debug("Creating new host '{}' using provider '{}'", target_host.name, target_host.provider)
        provider = get_provider_instance(target_host.provider, mngr_ctx)

        logger.trace(
            "Creating host with tags={} build_args={} start_args={} lifecycle={} known_hosts={}",
            target_host.tags,
            target_host.build.build_args,
            target_host.build.start_args,
            target_host.lifecycle,
            len(target_host.environment.known_hosts),
        )
        return provider.create_host(
            name=target_host.name,
            tags=target_host.tags,
            build_args=target_host.build.build_args,
            start_args=target_host.build.start_args,
            lifecycle=target_host.lifecycle,
            known_hosts=target_host.environment.known_hosts,
        )
    else:
        # already have the host
        logger.trace("Using existing host id={}", target_host.id)
        return target_host
