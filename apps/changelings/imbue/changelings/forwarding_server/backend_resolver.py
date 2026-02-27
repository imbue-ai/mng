from abc import ABC
from abc import abstractmethod
from collections.abc import Mapping

from pydantic import Field

from imbue.imbue_common.mutable_model import MutableModel
from imbue.mng.primitives import AgentId


class BackendResolverInterface(MutableModel, ABC):
    """Resolves agent IDs to their backend server URLs."""

    @abstractmethod
    def get_backend_url(self, agent_id: AgentId) -> str | None:
        """Return the backend URL for an agent, or None if unknown/offline."""

    @abstractmethod
    def list_known_agent_ids(self) -> tuple[AgentId, ...]:
        """Return all known agent IDs."""


class StaticBackendResolver(BackendResolverInterface):
    """Resolves backend URLs from a static mapping provided at construction time."""

    url_by_agent_id: Mapping[str, str] = Field(
        frozen=True,
        description="Mapping of agent ID to backend URL",
    )

    def get_backend_url(self, agent_id: AgentId) -> str | None:
        return self.url_by_agent_id.get(str(agent_id))

    def list_known_agent_ids(self) -> tuple[AgentId, ...]:
        return tuple(AgentId(agent_id) for agent_id in sorted(self.url_by_agent_id.keys()))
