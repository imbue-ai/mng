"""SSH provider instance implementation.

Manages connections to pre-configured SSH hosts.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from typing import Mapping
from typing import Sequence

from loguru import logger
from pydantic import Field
from pyinfra.api import Host as PyinfraHost
from pyinfra.api import State as PyinfraState
from pyinfra.api.exceptions import ConnectError as PyinfraConnectError
from pyinfra.api.inventory import Inventory

from imbue.mngr.errors import HostNotFoundError
from imbue.mngr.errors import SnapshotsNotSupportedError
from imbue.mngr.errors import UserInputError
from imbue.mngr.hosts.host import Host
from imbue.mngr.interfaces.data_types import CpuResources
from imbue.mngr.interfaces.data_types import HostResources
from imbue.mngr.interfaces.data_types import PyinfraConnector
from imbue.mngr.interfaces.data_types import SnapshotInfo
from imbue.mngr.interfaces.data_types import VolumeInfo
from imbue.mngr.interfaces.host import HostInterface
from imbue.mngr.primitives import HostId
from imbue.mngr.primitives import HostName
from imbue.mngr.primitives import ImageReference
from imbue.mngr.primitives import SnapshotId
from imbue.mngr.primitives import SnapshotName
from imbue.mngr.primitives import VolumeId
from imbue.imbue_common.frozen_model import FrozenModel
from imbue.mngr.providers.base_provider import BaseProviderInstance


class SSHHostConfig(FrozenModel):
    """Configuration for a single SSH host in the pool."""

    address: str = Field(description="SSH hostname or IP address")
    port: int = Field(default=22, description="SSH port number")
    user: str = Field(default="root", description="SSH username")
    key_file: Path | None = Field(default=None, description="Path to SSH private key file")


class SSHProviderInstance(BaseProviderInstance):
    """Provider instance for managing SSH hosts.

    Connects to pre-configured hosts via SSH. Hosts are statically defined
    in the configuration - this provider does not create or destroy hosts.

    Tags and snapshots are not supported.
    """

    hosts: dict[str, SSHHostConfig] = Field(
        frozen=True,
        description="Map of host name to SSH configuration",
    )
    local_state_dir: Path = Field(
        frozen=True,
        description="Local directory for storing provider state (host registrations, etc.)",
    )

    @property
    def supports_snapshots(self) -> bool:
        return False

    @property
    def supports_volumes(self) -> bool:
        return False

    @property
    def supports_mutable_tags(self) -> bool:
        return False

    def _get_host_state_path(self, host_name: str) -> Path:
        """Get the path to the host state file (stored locally)."""
        return self.local_state_dir / "providers" / "ssh" / f"{host_name}.json"

    def _read_host_state(self, host_name: str) -> dict[str, Any] | None:
        """Read host state from disk."""
        state_path = self._get_host_state_path(host_name)
        if not state_path.exists():
            return None
        return json.loads(state_path.read_text())

    def _write_host_state(self, host_name: str, state: dict[str, Any]) -> None:
        """Write host state to disk."""
        state_path = self._get_host_state_path(host_name)
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(state, indent=2))

    def _delete_host_state(self, host_name: str) -> None:
        """Delete host state from disk."""
        state_path = self._get_host_state_path(host_name)
        if state_path.exists():
            state_path.unlink()

    def _get_host_config_by_name(self, name: HostName) -> tuple[str, SSHHostConfig] | None:
        """Find host config by name."""
        name_str = str(name)
        if name_str in self.hosts:
            return name_str, self.hosts[name_str]
        return None

    def _get_host_config_by_id(self, host_id: HostId) -> tuple[str, SSHHostConfig] | None:
        """Find host config by ID (looks up in state files)."""
        # Search through all host state files
        state_dir = self.local_state_dir / "providers" / "ssh"
        if not state_dir.exists():
            return None

        for state_file in state_dir.glob("*.json"):
            host_name = state_file.stem
            state = self._read_host_state(host_name)
            if state and state.get("host_id") == str(host_id):
                if host_name in self.hosts:
                    return host_name, self.hosts[host_name]
        return None

    def _create_pyinfra_host(self, host_config: SSHHostConfig) -> PyinfraHost:
        """Create a pyinfra host with SSH connector."""
        host_data: dict[str, Any] = {
            "ssh_user": host_config.user,
            "ssh_port": host_config.port,
        }
        if host_config.key_file is not None:
            host_data["ssh_key"] = str(host_config.key_file)

        names_data = ([(host_config.address, host_data)], {})
        inventory = Inventory(names_data)
        state = PyinfraState(inventory=inventory)

        pyinfra_host = inventory.get_host(host_config.address)
        pyinfra_host.init(state)

        return pyinfra_host

    def _create_host_object(
        self,
        host_id: HostId,
        host_name: str,
        host_config: SSHHostConfig,
    ) -> Host:
        """Create a Host object for the given configuration."""
        pyinfra_host = self._create_pyinfra_host(host_config)
        connector = PyinfraConnector(pyinfra_host)

        return Host(
            id=host_id,
            connector=connector,
            provider_instance=self,
            mngr_ctx=self.mngr_ctx,
        )

    # =========================================================================
    # Core Lifecycle Methods
    # =========================================================================

    def create_host(
        self,
        name: HostName,
        image: ImageReference | None = None,
        tags: Mapping[str, str] | None = None,
        build_args: Sequence[str] | None = None,
        start_args: Sequence[str] | None = None,
    ) -> Host:
        """Create (register) a host from the configured host pool.

        This doesn't actually create a host - the host must already exist.
        Instead, it registers the host for use with mngr by creating state.
        """
        name_str = str(name)

        # Check if host exists in configuration
        if name_str not in self.hosts:
            available = ", ".join(self.hosts.keys()) if self.hosts else "(none)"
            raise UserInputError(
                f"Host '{name_str}' is not in the SSH host pool configuration. "
                f"Available hosts: {available}"
            )

        # Check if host is already registered
        existing_state = self._read_host_state(name_str)
        if existing_state is not None:
            raise UserInputError(
                f"Host '{name_str}' is already registered. Use 'mngr destroy {name_str}' first."
            )

        host_config = self.hosts[name_str]
        host_id = HostId.generate()

        logger.info(
            "Registering SSH host: name={}, address={}:{}",
            name_str,
            host_config.address,
            host_config.port,
        )

        # Create state file
        state = {
            "host_id": str(host_id),
            "host_name": name_str,
        }
        self._write_host_state(name_str, state)

        # Create the remote host directory
        host = self._create_host_object(host_id, name_str, host_config)
        host.execute_command(f"mkdir -p {self.host_dir}")

        logger.info("SSH host registered: id={}, name={}", host_id, name_str)
        return host

    def stop_host(
        self,
        host: HostInterface | HostId,
        create_snapshot: bool = True,
        timeout_seconds: float = 60.0,
    ) -> None:
        """Stop a host (no-op for SSH provider - hosts are always running)."""
        logger.debug("stop_host called for SSH provider (no-op)")

    def start_host(
        self,
        host: HostInterface | HostId,
        snapshot_id: SnapshotId | None = None,
    ) -> Host:
        """Start a host (returns the host if registered)."""
        host_id = host.id if isinstance(host, HostInterface) else host

        result = self._get_host_config_by_id(host_id)
        if result is None:
            raise HostNotFoundError(host_id)

        host_name, host_config = result
        return self._create_host_object(host_id, host_name, host_config)

    def destroy_host(
        self,
        host: HostInterface | HostId,
        delete_snapshots: bool = True,
    ) -> None:
        """Destroy (unregister) a host.

        This doesn't actually destroy the host - it just removes the mngr state.
        """
        host_id = host.id if isinstance(host, HostInterface) else host

        result = self._get_host_config_by_id(host_id)
        if result is None:
            raise HostNotFoundError(host_id)

        host_name, _ = result
        logger.info("Unregistering SSH host: id={}, name={}", host_id, host_name)
        self._delete_host_state(host_name)

    # =========================================================================
    # Discovery Methods
    # =========================================================================

    def get_host(
        self,
        host: HostId | HostName,
    ) -> Host:
        """Get a host by ID or name."""
        if isinstance(host, HostId):
            result = self._get_host_config_by_id(host)
            if result is None:
                raise HostNotFoundError(host)
            host_name, host_config = result
            return self._create_host_object(host, host_name, host_config)

        # Search by name
        name_str = str(host)
        state = self._read_host_state(name_str)
        if state is None or name_str not in self.hosts:
            raise HostNotFoundError(host)

        host_id = HostId(state["host_id"])
        host_config = self.hosts[name_str]
        return self._create_host_object(host_id, name_str, host_config)

    def list_hosts(
        self,
        include_destroyed: bool = False,
    ) -> list[HostInterface]:
        """List all registered hosts."""
        hosts: list[HostInterface] = []

        state_dir = self.local_state_dir / "providers" / "ssh"
        if not state_dir.exists():
            return hosts

        for state_file in state_dir.glob("*.json"):
            host_name = state_file.stem
            if host_name not in self.hosts:
                # Host was removed from config but state still exists
                continue

            state = self._read_host_state(host_name)
            if state is None:
                continue

            host_id = HostId(state["host_id"])
            host_config = self.hosts[host_name]
            try:
                host = self._create_host_object(host_id, host_name, host_config)
                hosts.append(host)
            except PyinfraConnectError as e:
                logger.debug("Failed to create host object for {}: {}", host_name, e)

        return hosts

    def get_host_resources(self, host: HostInterface) -> HostResources:
        """Get resource information for a host."""
        # SSH provider doesn't track resources - return defaults
        return HostResources(
            cpu=CpuResources(count=1, frequency_ghz=None),
            memory_gb=1.0,
            disk_gb=None,
            gpu=None,
        )

    # =========================================================================
    # Snapshot Methods (not supported)
    # =========================================================================

    def create_snapshot(
        self,
        host: HostInterface | HostId,
        name: SnapshotName | None = None,
    ) -> SnapshotId:
        raise SnapshotsNotSupportedError(self.name)

    def list_snapshots(
        self,
        host: HostInterface | HostId,
    ) -> list[SnapshotInfo]:
        return []

    def delete_snapshot(
        self,
        host: HostInterface | HostId,
        snapshot_id: SnapshotId,
    ) -> None:
        raise SnapshotsNotSupportedError(self.name)

    # =========================================================================
    # Volume Methods (not supported)
    # =========================================================================

    def list_volumes(self) -> list[VolumeInfo]:
        return []

    def delete_volume(self, volume_id: VolumeId) -> None:
        raise NotImplementedError("SSH provider does not support volumes")

    # =========================================================================
    # Tag Methods (not supported for SSH provider)
    # =========================================================================

    def get_host_tags(
        self,
        host: HostInterface | HostId,
    ) -> dict[str, str]:
        """SSH provider does not support tags - returns empty dict."""
        return {}

    def set_host_tags(
        self,
        host: HostInterface | HostId,
        tags: Mapping[str, str],
    ) -> None:
        """SSH provider does not support tags - no-op."""
        pass

    def add_tags_to_host(
        self,
        host: HostInterface | HostId,
        tags: Mapping[str, str],
    ) -> None:
        """SSH provider does not support tags - no-op."""
        pass

    def remove_tags_from_host(
        self,
        host: HostInterface | HostId,
        keys: Sequence[str],
    ) -> None:
        """SSH provider does not support tags - no-op."""
        pass

    def rename_host(
        self,
        host: HostInterface | HostId,
        name: HostName,
    ) -> Host:
        """Rename a host."""
        host_id = host.id if isinstance(host, HostInterface) else host

        result = self._get_host_config_by_id(host_id)
        if result is None:
            raise HostNotFoundError(host_id)

        old_name, host_config = result
        new_name = str(name)

        # Can only rename to a host that exists in configuration
        if new_name not in self.hosts:
            available = ", ".join(self.hosts.keys()) if self.hosts else "(none)"
            raise UserInputError(
                f"Cannot rename to '{new_name}' - not in SSH host pool configuration. "
                f"Available hosts: {available}"
            )

        # Update state file
        self._delete_host_state(old_name)
        state = {
            "host_id": str(host_id),
            "host_name": new_name,
        }
        self._write_host_state(new_name, state)

        return self._create_host_object(host_id, new_name, self.hosts[new_name])

    # =========================================================================
    # Connector Method
    # =========================================================================

    def get_connector(
        self,
        host: HostInterface | HostId,
    ) -> PyinfraHost:
        """Get a pyinfra connector for the host."""
        host_id = host.id if isinstance(host, HostInterface) else host

        result = self._get_host_config_by_id(host_id)
        if result is None:
            raise HostNotFoundError(host_id)

        _, host_config = result
        return self._create_pyinfra_host(host_config)

    # =========================================================================
    # Lifecycle Methods
    # =========================================================================

    def close(self) -> None:
        """Clean up resources (no-op for SSH provider)."""
        pass
