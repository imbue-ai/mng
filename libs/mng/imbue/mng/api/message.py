from collections.abc import Callable
from threading import Lock
from typing import Any

from loguru import logger
from pydantic import Field

from imbue.concurrency_group.executor import ConcurrencyGroupExecutor
from imbue.imbue_common.logging import log_call
from imbue.imbue_common.logging import log_span
from imbue.imbue_common.mutable_model import MutableModel
from imbue.mng.api.find import ensure_agent_started
from imbue.mng.api.find import ensure_host_started
from imbue.mng.api.list import load_all_agents_grouped_by_host
from imbue.mng.config.data_types import MngContext
from imbue.mng.errors import AgentNotFoundOnHostError
from imbue.mng.errors import BaseMngError
from imbue.mng.errors import HostOfflineError
from imbue.mng.errors import MngError
from imbue.mng.errors import ProviderInstanceNotFoundError
from imbue.mng.interfaces.agent import AgentInterface
from imbue.mng.interfaces.host import OnlineHostInterface
from imbue.mng.primitives import AgentLifecycleState
from imbue.mng.primitives import ErrorBehavior
from imbue.mng.utils.cel_utils import apply_cel_filters_to_context
from imbue.mng.utils.cel_utils import compile_cel_filters


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
    mng_ctx: MngContext,
    message_content: str,
    # CEL expressions - only include agents matching these
    include_filters: tuple[str, ...] = (),
    # CEL expressions - exclude agents matching these
    exclude_filters: tuple[str, ...] = (),
    # If True, send to all agents (filters still apply for exclusion)
    all_agents: bool = False,
    # How to handle errors (abort or continue)
    error_behavior: ErrorBehavior = ErrorBehavior.CONTINUE,
    # If True, automatically start offline hosts and stopped agents before sending
    is_start_desired: bool = False,
    # Optional callback invoked when message is sent successfully
    on_success: Callable[[str], None] | None = None,
    # Optional callback invoked when message fails (agent_name, error)
    on_error: Callable[[str, str], None] | None = None,
) -> MessageResult:
    """Send a message to agents matching the specified criteria.

    Messages are sent concurrently so that one agent's failure does not block or kill
    messages to other agents.
    """
    result = MessageResult()
    result_lock = Lock()

    # Compile CEL filters if provided
    compiled_include_filters: list[Any] = []
    compiled_exclude_filters: list[Any] = []
    if include_filters or exclude_filters:
        with log_span("Compiling CEL filters", include_filters=include_filters, exclude_filters=exclude_filters):
            compiled_include_filters, compiled_exclude_filters = compile_cel_filters(include_filters, exclude_filters)

    # Load all agents grouped by host
    with log_span("Loading agents from all providers"):
        agents_by_host, providers = load_all_agents_grouped_by_host(mng_ctx)
    provider_map = {provider.name: provider for provider in providers}
    logger.trace("Found {} hosts with agents", len(agents_by_host))

    # Phase 1: Resolve hosts and filter agents (sequential -- this is fast)
    agents_to_message: list[tuple[AgentInterface, OnlineHostInterface]] = []

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

            # If host is offline, optionally start it or report an error
            if not isinstance(host_interface, OnlineHostInterface):
                if is_start_desired:
                    host, _was_started = ensure_host_started(host_interface, is_start_desired=True, provider=provider)
                else:
                    exception = HostOfflineError(f"Host '{host_ref.host_id}' is offline. Cannot send messages.")
                    if error_behavior == ErrorBehavior.ABORT:
                        raise exception
                    logger.warning("Host is offline: {}", host_ref.host_id)
                    for agent_ref in agent_refs:
                        result.failed_agents.append((str(agent_ref.agent_name), str(exception)))
                        if on_error:
                            on_error(str(agent_ref.agent_name), str(exception))
                    continue
            else:
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

                    agents_to_message.append((agent, host))

                except MngError as e:
                    if error_behavior == ErrorBehavior.ABORT:
                        raise
                    error_msg = str(e)
                    result.failed_agents.append((str(agent_ref.agent_name), error_msg))
                    if on_error:
                        on_error(str(agent_ref.agent_name), error_msg)

        except MngError as e:
            if error_behavior == ErrorBehavior.ABORT:
                raise
            logger.warning("Error accessing host {}: {}", host_ref.host_id, e)

    # Phase 2: Send messages concurrently
    with ConcurrencyGroupExecutor(
        parent_cg=mng_ctx.concurrency_group, name="send_message_to_agents", max_workers=32
    ) as executor:
        for agent, host in agents_to_message:
            executor.submit(
                _send_message_to_agent,
                agent=agent,
                host=host,
                message_content=message_content,
                result=result,
                result_lock=result_lock,
                is_start_desired=is_start_desired,
                on_success=on_success,
                on_error=on_error,
            )

    # In ABORT mode, raise if any agent failed
    if error_behavior == ErrorBehavior.ABORT and result.failed_agents:
        first_agent_name, first_error = result.failed_agents[0]
        raise MngError(f"Failed to send message to {first_agent_name}: {first_error}")

    return result


def _send_message_to_agent(
    agent: AgentInterface,
    host: OnlineHostInterface,
    message_content: str,
    result: MessageResult,
    result_lock: Lock,
    is_start_desired: bool,
    on_success: Callable[[str], None] | None,
    on_error: Callable[[str, str], None] | None,
) -> None:
    """Send a message to a single agent.

    Called from a worker thread. Known errors (BaseMngError) are recorded in `result`;
    unexpected exceptions propagate to the future and will crash with a traceback.
    """
    agent_name = str(agent.name)

    # Check if agent has a tmux session (only STOPPED agents cannot receive messages)
    lifecycle_state = agent.get_lifecycle_state()
    if lifecycle_state == AgentLifecycleState.STOPPED:
        if is_start_desired:
            ensure_agent_started(agent, host, is_start_desired=True)
        else:
            error_msg = f"Agent has no tmux session (state: {lifecycle_state.value})"
            with result_lock:
                result.failed_agents.append((agent_name, error_msg))
            if on_error:
                on_error(agent_name, error_msg)
            return

    try:
        with log_span("Sending message to agent {}", agent_name):
            agent.send_message(message_content)
        with result_lock:
            result.successful_agents.append(agent_name)
        if on_success:
            on_success(agent_name)
    except BaseMngError as e:
        error_msg = str(e)
        with result_lock:
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
