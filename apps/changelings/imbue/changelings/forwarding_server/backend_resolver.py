import json
from abc import ABC
from abc import abstractmethod
from collections.abc import Mapping
from pathlib import Path
from typing import Final

from loguru import logger
from pydantic import Field

from imbue.imbue_common.mutable_model import MutableModel
from imbue.mng.primitives import AgentId

BACKENDS_FILENAME: Final[str] = "backends.json"


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


class FileBackendResolver(BackendResolverInterface):
    """Resolves backend URLs by reading a JSON file from disk on each lookup.

    The JSON file is a simple mapping of agent_id (string) to backend URL (string).
    Re-reading on each call ensures newly deployed changelings are immediately available
    without restarting the forwarding server.
    """

    backends_path: Path = Field(
        frozen=True,
        description="Path to the backends.json file",
    )

    def get_backend_url(self, agent_id: AgentId) -> str | None:
        mapping = _load_backends_file(self.backends_path)
        return mapping.get(str(agent_id))

    def list_known_agent_ids(self) -> tuple[AgentId, ...]:
        mapping = _load_backends_file(self.backends_path)
        return tuple(AgentId(agent_id) for agent_id in sorted(mapping.keys()))


def _load_backends_file(path: Path) -> dict[str, str]:
    """Load the backends JSON file, returning an empty dict if missing or invalid."""
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("Failed to load backends from {}: {}", path, e)
        return {}
    if not isinstance(raw, dict):
        logger.warning("Backends file {} does not contain a JSON object", path)
        return {}
    return raw


def register_backend(backends_path: Path, agent_id: AgentId, backend_url: str) -> None:
    """Register a backend URL for an agent by writing to the backends JSON file.

    Reads the existing file (if any), adds/updates the entry, and writes back atomically.
    """
    backends_path.parent.mkdir(parents=True, exist_ok=True)

    existing = _load_backends_file(backends_path)
    existing[str(agent_id)] = backend_url
    backends_path.write_text(json.dumps(existing, indent=2))
