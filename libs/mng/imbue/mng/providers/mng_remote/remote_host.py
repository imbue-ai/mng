from typing import Any

from pydantic import Field

from imbue.mng.hosts.offline_host import OfflineHost
from imbue.mng.primitives import AgentReference
from imbue.mng.primitives import HostState


class RemoteHost(OfflineHost):
    """Host representing a host on a remote mng instance.

    Unlike OfflineHost (which derives state from certified data and provider
    capabilities), RemoteHost passes through the state reported by the remote
    API server directly. It also holds pre-fetched agent data so that the
    listing pipeline does not need a second API call.
    """

    remote_state: HostState = Field(
        frozen=True,
        description="Host state as reported by the remote API server",
    )
    remote_agent_data: tuple[dict[str, Any], ...] = Field(
        frozen=True,
        description="Pre-fetched agent data from the remote API server",
    )

    def get_state(self) -> HostState:
        """Return the state as reported by the remote API."""
        return self.remote_state

    def get_agent_references(self) -> list[AgentReference]:
        """Return agent references from pre-fetched API data."""
        agent_refs: list[AgentReference] = []
        for agent_data in self.remote_agent_data:
            ref = self._validate_and_create_agent_reference(agent_data)
            if ref is not None:
                agent_refs.append(ref)
        return agent_refs
