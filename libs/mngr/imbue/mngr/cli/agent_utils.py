"""Shared utilities for CLI commands that work with agents."""

from imbue.mngr.api.find import find_and_maybe_start_agent_by_name_or_id
from imbue.mngr.api.list import list_agents
from imbue.mngr.api.list import load_all_agents_grouped_by_host
from imbue.mngr.cli.connect import select_agent_interactively
from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.errors import UserInputError
from imbue.mngr.interfaces.agent import AgentInterface
from imbue.mngr.interfaces.host import OnlineHostInterface
from imbue.mngr.primitives import AgentReference
from imbue.mngr.primitives import HostId
from imbue.mngr.primitives import HostName
from imbue.mngr.primitives import HostReference


def _host_matches_filter(host_ref: HostReference, host_filter: str) -> bool:
    """Check if a host reference matches the given filter string.

    The filter can be either a HostId (UUID) or a HostName.
    """
    # Try matching as HostId first
    try:
        filter_as_id = HostId(host_filter)
        if host_ref.host_id == filter_as_id:
            return True
    except ValueError:
        pass

    # Try matching as HostName
    filter_as_name = HostName(host_filter)
    return host_ref.host_name == filter_as_name


def filter_agents_by_host(
    agents_by_host: dict[HostReference, list[AgentReference]],
    host_filter: str,
) -> dict[HostReference, list[AgentReference]]:
    """Filter the agents_by_host mapping to only include hosts matching the filter.

    Raises UserInputError if no hosts match the filter.
    """
    filtered = {
        host_ref: agent_refs
        for host_ref, agent_refs in agents_by_host.items()
        if _host_matches_filter(host_ref, host_filter)
    }
    if not filtered:
        raise UserInputError(f"No host found matching: {host_filter}")
    return filtered


def select_agent_interactively_with_host(
    mngr_ctx: MngrContext,
) -> tuple[AgentInterface, OnlineHostInterface] | None:
    """Show interactive UI to select an agent.

    Returns tuple of (agent, host) or None if user quit without selecting.
    """
    list_result = list_agents(mngr_ctx)
    if not list_result.agents:
        raise UserInputError("No agents found")

    selected = select_agent_interactively(list_result.agents)
    if selected is None:
        return None

    # Find the actual agent and host from the selection
    agents_by_host, _ = load_all_agents_grouped_by_host(mngr_ctx)
    return find_and_maybe_start_agent_by_name_or_id(str(selected.id), agents_by_host, mngr_ctx, "select")
