import json
from abc import ABC
from abc import abstractmethod
from collections.abc import Mapping
from pathlib import Path
from typing import Final

from loguru import logger
from pydantic import Field

from imbue.imbue_common.frozen_model import FrozenModel
from imbue.imbue_common.mutable_model import MutableModel
from imbue.mng.primitives import AgentId

SERVERS_LOG_FILENAME: Final[str] = "servers.jsonl"


class ServerLogRecord(FrozenModel):
    """A record of a server started by an agent, as written to servers.jsonl.

    Each line of servers.jsonl is a JSON object with these fields.
    Agents write these records on startup so the forwarding server can discover them.
    """

    server: str = Field(description="Name of the server (e.g., 'web')")
    url: str = Field(description="URL where the server is accessible (e.g., 'http://localhost:9100/')")


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


class AgentLogsBackendResolver(BackendResolverInterface):
    """Resolves backend URLs by reading servers.jsonl from agent log directories.

    Each agent writes server information to $MNG_AGENT_STATE_DIR/logs/servers.jsonl
    when it starts. This resolver reads those files to discover which servers are running.

    Re-reading on each call ensures newly deployed changelings are immediately available
    without restarting the forwarding server.
    """

    host_dir: Path = Field(
        frozen=True,
        description="The mng host directory (e.g., ~/.mng) containing agent data",
    )

    def get_backend_url(self, agent_id: AgentId) -> str | None:
        servers_path = self._get_servers_log_path(agent_id)
        records = _load_server_log_records(servers_path)
        if not records:
            return None
        return records[-1].url

    def list_known_agent_ids(self) -> tuple[AgentId, ...]:
        agents_dir = self.host_dir / "agents"
        if not agents_dir.is_dir():
            return ()
        agent_ids: list[AgentId] = []
        for entry in sorted(agents_dir.iterdir()):
            if not entry.is_dir():
                continue
            servers_path = entry / "logs" / SERVERS_LOG_FILENAME
            if servers_path.exists():
                records = _load_server_log_records(servers_path)
                if records:
                    agent_ids.append(AgentId(entry.name))
        return tuple(agent_ids)

    def _get_servers_log_path(self, agent_id: AgentId) -> Path:
        return self.host_dir / "agents" / str(agent_id) / "logs" / SERVERS_LOG_FILENAME


def _load_server_log_records(path: Path) -> list[ServerLogRecord]:
    """Load server log records from a JSONL file, returning an empty list if missing or invalid."""
    if not path.exists():
        return []
    try:
        text = path.read_text()
    except OSError as e:
        logger.warning("Failed to read servers log from {}: {}", path, e)
        return []
    records: list[ServerLogRecord] = []
    for line in text.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            raw = json.loads(line)
            records.append(ServerLogRecord.model_validate(raw))
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning("Skipping invalid record in {}: {}", path, e)
    return records
