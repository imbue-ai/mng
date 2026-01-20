import time
from typing import cast

from loguru import logger

from imbue.mngr.api.data_types import CreateAgentResult
from imbue.mngr.api.data_types import NewHostOptions
from imbue.mngr.api.data_types import OnBeforeCreateArgs
from imbue.mngr.api.providers import get_provider_instance
from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.hosts.host import HostLocation
from imbue.mngr.interfaces.host import CreateAgentOptions
from imbue.mngr.interfaces.host import HostInterface
from imbue.mngr.utils.logging import log_call


def _call_on_before_create_hooks(
    mngr_ctx: MngrContext,
    target_host: HostInterface | NewHostOptions,
    agent_options: CreateAgentOptions,
    create_work_dir: bool,
) -> tuple[HostInterface | NewHostOptions, CreateAgentOptions, bool]:
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
    target_host: HostInterface | NewHostOptions,
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
    logger.debug("Starting agent {}", agent.name)
    host.start_agents([agent.id])

    # Send initial message if one is configured
    initial_message = agent.get_initial_message()
    if initial_message is not None:
        # Note: ideally agents would have their own mechanism for signaling readiness
        # (e.g., claude has hooks we could use). For now, use configurable delay.
        # Give the agent a moment to start up before sending the message
        logger.debug("Waiting for agent to become ready before sending initial message")
        time.sleep(agent_options.message_delay_seconds)
        logger.debug("Sending initial message to agent {}", agent.name)
        agent.send_message(initial_message)

    # Build and return the result
    return CreateAgentResult(agent=agent, host=host)


def resolve_target_host(
    target_host: HostInterface | NewHostOptions,
    mngr_ctx: MngrContext,
) -> HostInterface:
    """Resolve which host to use for the agent."""
    if target_host is not None and isinstance(target_host, NewHostOptions):
        # Create a new host using the specified provider
        logger.debug("Creating new host '{}' using provider '{}'", target_host.name, target_host.provider)
        provider = get_provider_instance(target_host.provider, mngr_ctx)
        logger.trace(
            "Creating host with image={} tags={} build_args={} start_args={}",
            target_host.build.image,
            target_host.tags,
            target_host.build.build_args,
            target_host.build.start_args,
        )
        return provider.create_host(
            name=target_host.name,
            image=target_host.build.image,
            tags=target_host.tags,
            build_args=target_host.build.build_args,
            start_args=target_host.build.start_args,
        )
    else:
        # already have the host
        logger.trace("Using existing host id={}", target_host.id)
        return target_host
