"""Shared utilities for CLI commands that work with agents."""

from imbue.mngr.api.list import list_agents
from imbue.mngr.api.list import load_all_agents_grouped_by_host
from imbue.mngr.api.providers import get_provider_instance
from imbue.mngr.cli.connect import select_agent_interactively
from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.errors import AgentNotFoundError
from imbue.mngr.errors import MngrError
from imbue.mngr.errors import UserInputError
from imbue.mngr.interfaces.agent import AgentInterface
from imbue.mngr.interfaces.host import OnlineHostInterface
from imbue.mngr.primitives import AgentId
from imbue.mngr.primitives import AgentName
from imbue.mngr.primitives import AgentReference
from imbue.mngr.primitives import HostReference


def find_agent_by_name_or_id(
    agent_str: str,
    agents_by_host: dict[HostReference, list[AgentReference]],
    mngr_ctx: MngrContext,
) -> tuple[AgentInterface, OnlineHostInterface]:
    """Find an agent by name or ID.

    Searches through the provided agents_by_host mapping to find an agent
    matching the given string (which can be either an agent ID or name).

    Returns tuple of (agent, host) or raises AgentNotFoundError/UserInputError.
    """
    # Try parsing as an AgentId first
    try:
        agent_id = AgentId(agent_str)
        # Search for the agent by ID
        for host_ref, agent_refs in agents_by_host.items():
            for agent_ref in agent_refs:
                if agent_ref.agent_id == agent_id:
                    provider = get_provider_instance(host_ref.provider_name, mngr_ctx)
                    host = provider.get_host(host_ref.host_id)
                    if not isinstance(host, OnlineHostInterface):
                        raise MngrError(f"Host {host_ref.host_id} is not online")
                    for agent in host.get_agents():
                        if agent.id == agent_id:
                            return agent, host
        raise AgentNotFoundError(agent_id)
    except ValueError:
        pass

    # Try matching by name
    agent_name = AgentName(agent_str)
    matching: list[tuple[AgentInterface, OnlineHostInterface]] = []

    for host_ref, agent_refs in agents_by_host.items():
        for agent_ref in agent_refs:
            if agent_ref.agent_name == agent_name:
                provider = get_provider_instance(host_ref.provider_name, mngr_ctx)
                host = provider.get_host(host_ref.host_id)
                # Skip offline hosts when searching by name
                if not isinstance(host, OnlineHostInterface):
                    continue
                for agent in host.get_agents():
                    if agent.name == agent_name:
                        matching.append((agent, host))

    if not matching:
        raise UserInputError(f"No agent found with name or ID: {agent_str}")

    if len(matching) > 1:
        raise UserInputError(
            f"Multiple agents found with name '{agent_str}'. Please use the agent ID instead, or specify the host."
        )

    return matching[0]


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
    return find_agent_by_name_or_id(str(selected.id), agents_by_host, mngr_ctx)
