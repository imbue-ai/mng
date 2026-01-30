from abc import ABC
from abc import abstractmethod
from pathlib import Path
from typing import Mapping
from typing import Sequence

from pydantic import Field
from pyinfra.api.host import Host as PyinfraHost

from imbue.imbue_common.mutable_model import MutableModel
from imbue.mngr.api.data_types import HostLifecycleOptions
from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.interfaces.data_types import HostResources
from imbue.mngr.interfaces.data_types import SnapshotInfo
from imbue.mngr.interfaces.data_types import VolumeInfo
from imbue.mngr.interfaces.host import HostInterface
from imbue.mngr.primitives import AgentId
from imbue.mngr.primitives import HostId
from imbue.mngr.primitives import HostName
from imbue.mngr.primitives import ImageReference
from imbue.mngr.primitives import ProviderInstanceName
from imbue.mngr.primitives import SnapshotId
from imbue.mngr.primitives import SnapshotName
from imbue.mngr.primitives import VolumeId


class ProviderInstanceInterface(MutableModel, ABC):
    """A ProviderInstance is a configured endpoint that creates and manages hosts.

    Each provider instance is created by a ProviderBackend.
    """

    name: ProviderInstanceName = Field(frozen=True, description="Name of this provider instance")
    host_dir: Path = Field(frozen=True, description="Base directory for mngr data on hosts managed by this instance")
    mngr_ctx: MngrContext = Field(frozen=True, repr=False, description="The mngr context")

    # =========================================================================
    # Capability Properties
    # =========================================================================

    @property
    @abstractmethod
    def is_authorized(self) -> bool:
        """Whether this provider instance is authorized/authenticated.

        For providers that require authentication (like Modal), this checks if
        valid credentials are available. For providers that don't require auth
        (like local), this always returns True.

        When a provider is not authorized:
        - list_hosts() should warn and return empty list
        - create_host() and other write operations should raise ProviderNotAuthorizedError
        """
        ...

    @property
    @abstractmethod
    def supports_snapshots(self) -> bool:
        """Whether this provider supports creating and managing host snapshots."""
        ...

    @property
    @abstractmethod
    def supports_volumes(self) -> bool:
        """Whether this provider supports volume management."""
        ...

    @property
    @abstractmethod
    def supports_mutable_tags(self) -> bool:
        """Whether this provider supports modifying tags after host creation.

        Some providers (like Docker) store tags as immutable labels that cannot be
        changed after container creation. Others (like local) store tags in mutable
        files that can be updated at any time.
        """
        ...

    # =========================================================================
    # Core Lifecycle Methods
    # =========================================================================

    @abstractmethod
    def create_host(
        self,
        name: HostName,
        image: ImageReference | None = None,
        tags: Mapping[str, str] | None = None,
        build_args: Sequence[str] | None = None,
        start_args: Sequence[str] | None = None,
        lifecycle: HostLifecycleOptions | None = None,
    ) -> HostInterface:
        """Create and start a new host with the given name and configuration."""
        ...

    @abstractmethod
    def stop_host(
        self,
        host: HostInterface | HostId,
        create_snapshot: bool = True,
        timeout_seconds: float = 60.0,
    ) -> None:
        """Stop a running host, optionally creating a snapshot before stopping."""
        ...

    @abstractmethod
    def start_host(
        self,
        host: HostInterface | HostId,
        snapshot_id: SnapshotId | None = None,
    ) -> HostInterface:
        """Start a stopped host, optionally restoring from a specific snapshot."""
        ...

    @abstractmethod
    def destroy_host(
        self,
        host: HostInterface | HostId,
        delete_snapshots: bool = True,
    ) -> None:
        """Permanently destroy a host and optionally delete its snapshots."""
        ...

    # =========================================================================
    # Discovery Methods
    # =========================================================================

    @abstractmethod
    def get_host(
        self,
        host: HostId | HostName,
    ) -> HostInterface:
        """Retrieve a host by its ID or name, raising HostNotFoundError if not found."""
        ...

    @abstractmethod
    def list_hosts(
        self,
        include_destroyed: bool = False,
    ) -> list[HostInterface]:
        """List all hosts managed by this provider instance."""
        ...

    @abstractmethod
    def get_host_resources(self, host: HostInterface) -> HostResources:
        """Get CPU, memory, disk, and GPU resource information for a host."""
        ...

    # =========================================================================
    # Snapshot Methods
    # =========================================================================

    @abstractmethod
    def create_snapshot(
        self,
        host: HostInterface | HostId,
        name: SnapshotName | None = None,
    ) -> SnapshotId:
        """Create a snapshot of the host's current state and return its ID."""
        ...

    @abstractmethod
    def list_snapshots(
        self,
        host: HostInterface | HostId,
    ) -> list[SnapshotInfo]:
        """List all snapshots associated with a host."""
        ...

    @abstractmethod
    def delete_snapshot(
        self,
        host: HostInterface | HostId,
        snapshot_id: SnapshotId,
    ) -> None:
        """Delete a snapshot by its ID."""
        ...

    # =========================================================================
    # Volume Methods
    # =========================================================================

    @abstractmethod
    def list_volumes(self) -> list[VolumeInfo]:
        """List all volumes managed by this provider.

        Returns volumes with mngr- prefix in name or with mngr-managed tags.
        """
        ...

    @abstractmethod
    def delete_volume(self, volume_id: VolumeId) -> None:
        """Delete a volume.

        Raises MngrError if volume doesn't exist or can't be deleted.
        """
        ...

    # =========================================================================
    # Host Mutation Methods
    # =========================================================================

    @abstractmethod
    def get_host_tags(
        self,
        host: HostInterface | HostId,
    ) -> dict[str, str]:
        """Get all tags associated with a host as a key-value mapping."""
        ...

    @abstractmethod
    def set_host_tags(
        self,
        host: HostInterface | HostId,
        tags: Mapping[str, str],
    ) -> None:
        """Replace all tags on a host with the provided tags."""
        ...

    @abstractmethod
    def add_tags_to_host(
        self,
        host: HostInterface | HostId,
        tags: Mapping[str, str],
    ) -> None:
        """Add or update tags on a host without removing existing tags."""
        ...

    @abstractmethod
    def remove_tags_from_host(
        self,
        host: HostInterface | HostId,
        keys: Sequence[str],
    ) -> None:
        """Remove tags from a host by their keys."""
        ...

    @abstractmethod
    def rename_host(
        self,
        host: HostInterface | HostId,
        name: HostName,
    ) -> HostInterface:
        """Rename a host and return the updated host object."""
        ...

    # =========================================================================
    # Connector Method
    # =========================================================================

    @abstractmethod
    def get_connector(
        self,
        host: HostInterface | HostId,
    ) -> "PyinfraHost":
        """Get the pyinfra connector for executing operations on a host."""
        ...

    # =========================================================================
    # Lifecycle Methods
    # =========================================================================

    def close(self) -> None:
        """Clean up resources held by this provider instance.

        Providers that hold long-lived resources (like Modal app contexts) should
        override this method to release them. This method is called during shutdown
        via atexit handlers.

        The default implementation does nothing.
        """

    def list_persisted_agent_data_for_host(self, host_id: HostId) -> list[dict]:
        """List persisted agent data for a stopped host.

        Some providers (like Modal) persist agent state when hosts are stopped,
        allowing agent information to be retrieved even when the host is not running.

        Each dict in the returned list should contain at minimum an 'id' field with
        the agent ID. Returns an empty list if no persisted data exists or the
        provider doesn't support this feature.
        """
        return []

    def persist_agent_data(self, host_id: HostId, agent_data: Mapping[str, object]) -> None:
        """Persist agent data to external storage.

        Called when an agent is created or its data.json is updated. Providers
        that support persistent agent state (like Modal) should override this
        to write the agent data to their storage backend.

        The default implementation is a no-op for providers that don't need this.
        """

    def remove_persisted_agent_data(self, host_id: HostId, agent_id: AgentId) -> None:
        """Remove persisted agent data from external storage.

        Called when an agent is destroyed. Providers that support persistent
        agent state (like Modal) should override this to remove the agent data
        from their storage backend.

        The default implementation is a no-op for providers that don't need this.
        """
