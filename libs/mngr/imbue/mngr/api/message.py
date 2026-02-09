from collections.abc import Callable
from typing import Any

from loguru import logger
from pydantic import Field

from imbue.imbue_common.logging import log_call
from imbue.imbue_common.logging import log_span
from imbue.imbue_common.mutable_model import MutableModel
from imbue.mngr.api.list import load_all_agents_grouped_by_host
from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.errors import AgentNotFoundOnHostError
from imbue.mngr.errors import HostOfflineError
from imbue.mngr.errors import MngrError
from imbue.mngr.errors import ProviderInstanceNotFoundError
from imbue.mngr.interfaces.agent import AgentInterface
from imbue.mngr.interfaces.host import OnlineHostInterface
from imbue.mngr.primitives import AgentLifecycleState
from imbue.mngr.primitives import ErrorBehavior
from imbue.mngr.utils.cel_utils import apply_cel_filters_to_context
from imbue.mngr.utils.cel_utils import compile_cel_filters


class MessageResult(MutableModel):
    """Result of sending messages to agents."""

    successful_agents: list[str] = Field(
        default_factory=list, description="List of agent names that received messages"
    )
    failed_agents: list[tuple[str, str]] = Field(
        default_factory=list, description="List of (agent_name, error_message) tuples"
    )


@log_call
def send_message_to_agents(
    mngr_ctx: MngrContext,
    message_content: str,
    # CEL expressions - only include agents matching these
    include_filters: tuple[str, ...] = (),
    # CEL expressions - exclude agents matching these
    exclude_filters: tuple[str, ...] = (),
    # If True, send to all agents (filters still apply for exclusion)
    all_agents: bool = False,
    # How to handle errors (abort or continue)
    error_behavior: ErrorBehavior = ErrorBehavior.CONTINUE,
    # Optional callback invoked when message is sent successfully
    on_success: Callable[[str], None] | None = None,
    # Optional callback invoked when message fails (agent_name, error)
    on_error: Callable[[str, str], None] | None = None,
) -> MessageResult:
    """Send a message to agents matching the specified criteria."""
    result = MessageResult()

    # Compile CEL filters if provided
    compiled_include_filters: list[Any] = []
    compiled_exclude_filters: list[Any] = []
    if include_filters or exclude_filters:
        with log_span("Compiling CEL filters"):
            compiled_include_filters, compiled_exclude_filters = compile_cel_filters(include_filters, exclude_filters)
        logger.trace(
            "Compiled {} include and {} exclude filters", len(compiled_include_filters), len(compiled_exclude_filters)
        )

    # Load all agents grouped by host
    with log_span("Loading agents from all providers"):
        agents_by_host, providers = load_all_agents_grouped_by_host(mngr_ctx)
    provider_map = {provider.name: provider for provider in providers}
    logger.trace("Found {} hosts with agents", len(agents_by_host))

    # Process each host and its agents
    for host_ref, agent_refs in agents_by_host.items():
        try:
            provider = provider_map.get(host_ref.provider_name)
            if not provider:
                exception = ProviderInstanceNotFoundError(host_ref.provider_name)
                if error_behavior == ErrorBehavior.ABORT:
                    raise exception
                logger.warning("Provider not found: {}", host_ref.provider_name)
                continue

            host_interface = provider.get_host(host_ref.host_id)

            # FIXME: much like how the connect command has an option for bringing a host online, we should have a similar option here (to bring online any specified host so that it can be messaged)
            #  Then this whole next block should be updated (to have a similar "ensure_host_online" and "ensure_agent_running" functions, and use that second one below)
            # Check if host is online - can't send messages to offline hosts
            if not isinstance(host_interface, OnlineHostInterface):
                exception = HostOfflineError(f"Host '{host_ref.host_id}' is offline. Cannot send messages.")
                if error_behavior == ErrorBehavior.ABORT:
                    raise exception
                logger.warning("Host is offline: {}", host_ref.host_id)
                for agent_ref in agent_refs:
                    result.failed_agents.append((str(agent_ref.agent_name), str(exception)))
                    if on_error:
                        on_error(str(agent_ref.agent_name), str(exception))
                continue
            host = host_interface

            # Get all agents on this host
            agents = host.get_agents()

            for agent_ref in agent_refs:
                try:
                    # Find the agent in the list
                    agent = next((a for a in agents if a.id == agent_ref.agent_id), None)

                    if agent is None:
                        exception = AgentNotFoundOnHostError(agent_ref.agent_id, host_ref.host_id)
                        if error_behavior == ErrorBehavior.ABORT:
                            raise exception
                        error_msg = str(exception)
                        result.failed_agents.append((str(agent_ref.agent_name), error_msg))
                        if on_error:
                            on_error(str(agent_ref.agent_name), error_msg)
                        continue

                    # Apply CEL filters if provided
                    if compiled_include_filters or compiled_exclude_filters or not all_agents:
                        agent_context = _agent_to_cel_context(agent, host_ref.provider_name)
                        is_included = apply_cel_filters_to_context(
                            context=agent_context,
                            include_filters=compiled_include_filters,
                            exclude_filters=compiled_exclude_filters,
                            error_context_description=f"agent {agent.name}",
                        )
                        # If not all_agents and no include filters, skip
                        if not all_agents and not include_filters and not is_included:
                            continue
                        if not is_included:
                            continue

                    # Send the message
                    _send_message_to_agent(
                        agent=agent,
                        message_content=message_content,
                        result=result,
                        error_behavior=error_behavior,
                        on_success=on_success,
                        on_error=on_error,
                    )

                except MngrError as e:
                    if error_behavior == ErrorBehavior.ABORT:
                        raise
                    error_msg = str(e)
                    result.failed_agents.append((str(agent_ref.agent_name), error_msg))
                    if on_error:
                        on_error(str(agent_ref.agent_name), error_msg)

        except MngrError as e:
            if error_behavior == ErrorBehavior.ABORT:
                raise
            logger.warning("Error accessing host {}: {}", host_ref.host_id, e)

    return result


def _send_message_to_agent(
    agent: AgentInterface,
    message_content: str,
    result: MessageResult,
    error_behavior: ErrorBehavior,
    on_success: Callable[[str], None] | None,
    on_error: Callable[[str, str], None] | None,
) -> None:
    """Send a message to a single agent."""
    agent_name = str(agent.name)

    # Check if agent has a tmux session (only STOPPED agents cannot receive messages)
    lifecycle_state = agent.get_lifecycle_state()
    if lifecycle_state == AgentLifecycleState.STOPPED:
        error_msg = f"Agent has no tmux session (state: {lifecycle_state.value})"
        if error_behavior == ErrorBehavior.ABORT:
            raise MngrError(f"Cannot send message to {agent_name}: {error_msg}")
        result.failed_agents.append((agent_name, error_msg))
        if on_error:
            on_error(agent_name, error_msg)
        return

    try:
        with log_span("Sending message to agent {}", agent_name):
            agent.send_message(message_content)
        result.successful_agents.append(agent_name)
        if on_success:
            on_success(agent_name)
    except MngrError as e:
        error_msg = str(e)
        if error_behavior == ErrorBehavior.ABORT:
            raise
        result.failed_agents.append((agent_name, error_msg))
        if on_error:
            on_error(agent_name, error_msg)


def _agent_to_cel_context(agent: AgentInterface, provider_name: str) -> dict[str, Any]:
    """Convert an agent to a CEL-friendly dict for filtering."""
    return {
        "id": str(agent.id),
        "name": str(agent.name),
        "type": str(agent.agent_type),
        "state": agent.get_lifecycle_state().value,
        "host": {
            "id": str(agent.host_id),
            "provider": provider_name,
        },
    }
