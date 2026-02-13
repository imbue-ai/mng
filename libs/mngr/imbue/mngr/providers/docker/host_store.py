import json
from pathlib import Path
from typing import Any

from loguru import logger
from pydantic import Field
from pydantic import PrivateAttr

from imbue.imbue_common.frozen_model import FrozenModel
from imbue.mngr.interfaces.data_types import CertifiedHostData
from imbue.mngr.interfaces.data_types import HostConfig
from imbue.mngr.primitives import AgentId
from imbue.mngr.primitives import HostId


class ContainerConfig(HostConfig):
    """Configuration parsed from build arguments for Docker containers."""

    gpu: str | None = Field(default=None, description="GPU access configuration (e.g., 'all', '0', 'nvidia')")
    cpu: float = Field(default=1.0, description="Number of CPU cores")
    memory: float = Field(default=1.0, description="Memory in GB")
    image: str | None = Field(default=None, description="Base Docker image name")
    dockerfile: str | None = Field(default=None, description="Path to Dockerfile for custom image build")
    context_dir: str | None = Field(default=None, description="Build context directory for Dockerfile")
    network: str | None = Field(default=None, description="Docker network to attach to")
    volumes: tuple[str, ...] = Field(default=(), description="Additional volume mounts (host:container[:mode])")
    ports: tuple[str, ...] = Field(default=(), description="Additional port mappings (host:container)")


class HostRecord(FrozenModel):
    """Host metadata stored in the local file store.

    This record contains all information needed to connect to and restore a host.
    It is stored at hosts/<host_id>.json in the provider data directory.

    For failed hosts (those that failed during creation), only certified_host_data
    is required. The SSH fields and config will be None since the host never started.
    """

    certified_host_data: CertifiedHostData = Field(
        frozen=True,
        description="The certified host data loaded from data.json",
    )
    ssh_host: str | None = Field(default=None, description="SSH hostname for connecting to the container")
    ssh_port: int | None = Field(default=None, description="SSH port number")
    ssh_host_public_key: str | None = Field(default=None, description="SSH host public key for verification")
    config: ContainerConfig | None = Field(default=None, description="Container configuration")
    container_id: str | None = Field(default=None, description="Docker container ID for reconnection")


class DockerHostStore(FrozenModel):
    """JSON file-based host record store for the Docker provider.

    Directory layout::

        <base_dir>/
            hosts/
                <host_id>.json
                <host_id>/
                    <agent_id>.json
    """

    base_dir: Path = Field(frozen=True, description="Root directory for the store")
    _cache: dict[HostId, HostRecord] = PrivateAttr(default_factory=dict)

    @property
    def hosts_dir(self) -> Path:
        return self.base_dir / "hosts"

    def _host_record_path(self, host_id: HostId) -> Path:
        return self.hosts_dir / f"{host_id}.json"

    def _agent_data_dir(self, host_id: HostId) -> Path:
        return self.hosts_dir / str(host_id)

    def _agent_data_path(self, host_id: HostId, agent_id: AgentId) -> Path:
        return self._agent_data_dir(host_id) / f"{agent_id}.json"

    def write_host_record(self, host_record: HostRecord) -> None:
        """Write a host record to disk."""
        host_id = HostId(host_record.certified_host_data.host_id)
        path = self._host_record_path(host_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = host_record.model_dump_json(indent=2)
        path.write_text(data)
        logger.trace("Wrote host record: {}", path)
        self._cache[host_id] = host_record

    def read_host_record(self, host_id: HostId, use_cache: bool = True) -> HostRecord | None:
        """Read a host record from disk. Returns None if not found."""
        if use_cache and host_id in self._cache:
            return self._cache[host_id]

        path = self._host_record_path(host_id)
        if not path.exists():
            return None

        try:
            data = path.read_text()
            host_record = HostRecord.model_validate_json(data)
            self._cache[host_id] = host_record
            return host_record
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning("Failed to read host record {}: {}", path, e)
            return None

    def delete_host_record(self, host_id: HostId) -> None:
        """Delete a host record and associated agent data."""
        agent_dir = self._agent_data_dir(host_id)
        if agent_dir.exists():
            for agent_file in agent_dir.iterdir():
                agent_file.unlink()
            agent_dir.rmdir()

        path = self._host_record_path(host_id)
        if path.exists():
            path.unlink()

        self._cache.pop(host_id, None)
        logger.trace("Deleted host record: {}", host_id)

    def list_all_host_records(self) -> list[HostRecord]:
        """List all host records stored on disk."""
        if not self.hosts_dir.exists():
            return []

        records: list[HostRecord] = []
        for path in self.hosts_dir.glob("*.json"):
            host_id_str = path.stem
            host_id = HostId(host_id_str)
            record = self.read_host_record(host_id, use_cache=False)
            if record is not None:
                records.append(record)

        return records

    def persist_agent_data(self, host_id: HostId, agent_data: dict[str, object]) -> None:
        """Write agent data for offline listing."""
        agent_id = agent_data.get("id")
        if not agent_id:
            logger.warning("Cannot persist agent data without id field")
            return

        path = self._agent_data_path(host_id, AgentId(str(agent_id)))
        path.parent.mkdir(parents=True, exist_ok=True)
        data = json.dumps(dict(agent_data), indent=2)
        path.write_text(data)
        logger.trace("Persisted agent data: {}", path)

    def list_persisted_agent_data_for_host(self, host_id: HostId) -> list[dict[str, Any]]:
        """Read persisted agent data for a host."""
        agent_dir = self._agent_data_dir(host_id)
        if not agent_dir.exists():
            return []

        agent_records: list[dict[str, Any]] = []
        for path in agent_dir.glob("*.json"):
            try:
                content = path.read_text()
                agent_data = json.loads(content)
                agent_records.append(agent_data)
            except (json.JSONDecodeError, OSError) as e:
                logger.trace("Skipped invalid agent record file {}: {}", path, e)
                continue

        return agent_records

    def remove_persisted_agent_data(self, host_id: HostId, agent_id: AgentId) -> None:
        """Remove persisted agent data."""
        path = self._agent_data_path(host_id, agent_id)
        if path.exists():
            path.unlink()
        logger.trace("Removed agent data: {}", path)

    def clear_cache(self) -> None:
        """Clear the in-memory cache."""
        self._cache.clear()
