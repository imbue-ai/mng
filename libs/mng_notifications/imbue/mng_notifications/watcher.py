import threading
import time
from collections.abc import Mapping
from collections.abc import Sequence

from loguru import logger

from imbue.imbue_common.pure import pure
from imbue.mng.api.list import list_agents
from imbue.mng.config.data_types import MngContext
from imbue.mng.interfaces.data_types import AgentDetails
from imbue.mng.primitives import AgentId
from imbue.mng.primitives import AgentLifecycleState
from imbue.mng.primitives import ErrorBehavior
from imbue.mng_notifications.config import NotificationsPluginConfig
from imbue.mng_notifications.notifier import Notifier
from imbue.mng_notifications.notifier import build_execute_command


@pure
def detect_waiting_transitions(
    previous_states: Mapping[AgentId, AgentLifecycleState],
    current_agents: Sequence[AgentDetails],
) -> list[AgentDetails]:
    """Return agents that have just transitioned from RUNNING to WAITING."""
    transitioned: list[AgentDetails] = []
    for agent in current_agents:
        prev = previous_states.get(agent.id)
        if prev == AgentLifecycleState.RUNNING and agent.state == AgentLifecycleState.WAITING:
            transitioned.append(agent)
    return transitioned


@pure
def build_state_map(current_agents: Sequence[AgentDetails]) -> dict[AgentId, AgentLifecycleState]:
    """Build a mapping of agent ID to lifecycle state from the current agent list."""
    return {agent.id: agent.state for agent in current_agents}


def watch_for_waiting_agents(
    mng_ctx: MngContext,
    interval_seconds: float,
    include_filters: tuple[str, ...],
    exclude_filters: tuple[str, ...],
    plugin_config: NotificationsPluginConfig,
    notifier: Notifier,
    stop_event: threading.Event | None = None,
) -> None:
    """Poll agents and send notifications when RUNNING -> WAITING transitions occur.

    Runs until stop_event is set (if provided) or until interrupted.
    """
    previous_states: dict[AgentId, AgentLifecycleState] = {}

    # Initial poll to establish baseline (no notifications on first poll)
    agents = _poll_agents(mng_ctx, include_filters, exclude_filters)
    if agents is not None:
        previous_states = build_state_map(agents)
        logger.info("Tracking {} agent(s)", len(previous_states))

    while stop_event is None or not stop_event.is_set():
        if stop_event is not None:
            stop_event.wait(timeout=interval_seconds)
            if stop_event.is_set():
                break
        else:
            time.sleep(interval_seconds)

        agents = _poll_agents(mng_ctx, include_filters, exclude_filters)
        if agents is None:
            continue

        transitioned = detect_waiting_transitions(previous_states, agents)
        for agent in transitioned:
            _notify_agent_waiting(agent, plugin_config, notifier)

        previous_states = build_state_map(agents)


def _poll_agents(
    mng_ctx: MngContext,
    include_filters: tuple[str, ...],
    exclude_filters: tuple[str, ...],
) -> list[AgentDetails] | None:
    """Poll all agents. Returns None if the poll fails."""
    try:
        result = list_agents(
            mng_ctx,
            is_streaming=False,
            include_filters=include_filters,
            exclude_filters=exclude_filters,
            error_behavior=ErrorBehavior.CONTINUE,
        )
        return result.agents
    except Exception:
        logger.opt(exception=True).debug("Failed to poll agents")
        return None


def _notify_agent_waiting(
    agent: AgentDetails,
    plugin_config: NotificationsPluginConfig,
    notifier: Notifier,
) -> None:
    """Send a notification that an agent has transitioned to WAITING."""
    title = "Agent waiting"
    message = f"{agent.name} is waiting for input"
    execute_command = build_execute_command(str(agent.name), plugin_config)
    logger.info("{} ({}): RUNNING -> WAITING", agent.name, agent.id)
    notifier.notify(title, message, execute_command)
