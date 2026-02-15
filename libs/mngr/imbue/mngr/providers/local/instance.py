import json
import shutil
from functools import cached_property
from pathlib import Path
from typing import Final
from typing import Mapping
from typing import Sequence

import psutil
from loguru import logger
from pyinfra.api import Host as PyinfraHost
from pyinfra.api import State
from pyinfra.api.inventory import Inventory

from imbue.concurrency_group.concurrency_group import ConcurrencyGroup
from imbue.imbue_common.logging import log_span
from imbue.mngr.api.data_types import HostLifecycleOptions
from imbue.mngr.errors import HostNotFoundError
from imbue.mngr.errors import LocalHostNotDestroyableError
from imbue.mngr.errors import LocalHostNotStoppableError
from imbue.mngr.errors import SnapshotsNotSupportedError
from imbue.mngr.hosts.host import Host
from imbue.mngr.interfaces.data_types import CpuResources
from imbue.mngr.interfaces.data_types import HostResources
from imbue.mngr.interfaces.data_types import PyinfraConnector
from imbue.mngr.interfaces.data_types import SnapshotInfo
from imbue.mngr.interfaces.data_types import VolumeInfo
from imbue.mngr.interfaces.host import HostInterface
from imbue.mngr.interfaces.volume import Volume
from imbue.mngr.primitives import ActivitySource
from imbue.mngr.primitives import HostId
from imbue.mngr.primitives import HostName
from imbue.mngr.primitives import ImageReference
from imbue.mngr.primitives import SnapshotId
from imbue.mngr.primitives import SnapshotName
from imbue.mngr.primitives import VolumeId
from imbue.mngr.providers.base_provider import BaseProviderInstance
from imbue.mngr.providers.local.volume import LocalVolume

LOCAL_PROVIDER_SUBDIR: Final[str] = "local"
VOLUMES_SUBDIR: Final[str] = "volumes"
HOST_ID_FILENAME: Final[str] = "host_id"
TAGS_FILENAME: Final[str] = "labels.json"


class LocalProviderInstance(BaseProviderInstance):
    """Provider instance for managing the local computer as a host.

    The local provider represents your local machine as a host. It has special
    semantics: the host cannot be stopped or destroyed, and snapshots are not
    supported. The host ID is persistent (generated once and saved to disk).
    """

    @property
    def supports_snapshots(self) -> bool:
        return False

    @property
    def supports_shutdown_hosts(self) -> bool:
        return True

    @property
    def supports_volumes(self) -> bool:
        return True

    @property
    def supports_mutable_tags(self) -> bool:
        return True

    @property
    def _volumes_dir(self) -> Path:
        """Get the directory for local volumes."""
        return self.mngr_ctx.config.default_host_dir.expanduser() / VOLUMES_SUBDIR

    @property
    def _provider_data_dir(self) -> Path:
        """Get the provider data directory path (not profile-specific, for tags etc)."""
        return self.mngr_ctx.config.default_host_dir.expanduser() / "providers" / LOCAL_PROVIDER_SUBDIR

    @property
    def _host_id_dir(self) -> Path:
        """Get the directory for host_id (global, not profile-specific).

        The host_id is stored at ~/.mngr/host_id because it identifies this local
        machine, not a particular profile. Different profiles on the same machine
        should share the same local host_id.
        """
        return self.mngr_ctx.config.default_host_dir.expanduser()

    def _ensure_provider_data_dir(self) -> None:
        """Ensure the provider data directory exists."""
        self._provider_data_dir.mkdir(parents=True, exist_ok=True)

    @cached_property
    def host_id(self) -> HostId:
        return self._get_or_create_host_id()

    def _get_or_create_host_id(self) -> HostId:
        """Get the persistent host ID, creating it if it doesn't exist.

        The host_id is stored globally at ~/.mngr/host_id (not per-profile)
        because it identifies the local machine itself, not a profile.
        """
        host_id_dir = self._host_id_dir
        host_id_dir.mkdir(parents=True, exist_ok=True)
        host_id_path = host_id_dir / HOST_ID_FILENAME

        if host_id_path.exists():
            host_id = HostId(host_id_path.read_text().strip())
            logger.trace("Loaded existing local host id={}", host_id)
            return host_id

        new_host_id = HostId.generate()
        host_id_path.write_text(new_host_id)
        logger.debug("Generated new local host id={}", new_host_id)
        return new_host_id

    def _get_tags_path(self) -> Path:
        """Get the path to the tags file."""
        return self._provider_data_dir / TAGS_FILENAME

    def _load_tags(self) -> dict[str, str]:
        """Load tags from the tags file."""
        tags_path = self._get_tags_path()
        if not tags_path.exists():
            return {}

        content = tags_path.read_text()
        if not content.strip():
            return {}

        data = json.loads(content)
        return {item["key"]: item["value"] for item in data}

    def _save_tags(self, tags: Mapping[str, str]) -> None:
        """Save tags to the tags file."""
        self._ensure_provider_data_dir()
        tags_path = self._get_tags_path()
        data = [{"key": key, "value": value} for key, value in tags.items()]
        tags_path.write_text(json.dumps(data, indent=2))

    def _create_local_pyinfra_host(self) -> PyinfraHost:
        """Create a pyinfra host for local execution.

        When the host name starts with '@', pyinfra automatically uses the
        LocalConnector, which executes commands locally without SSH.
        The host must be initialized with a State for connection to work.
        """
        names_data = (["@local"], {})
        inventory = Inventory(names_data)
        state = State(inventory=inventory)
        pyinfra_host = inventory.get_host("@local")
        pyinfra_host.init(state)
        return pyinfra_host

    def _create_host(self, name: HostName, tags: Mapping[str, str] | None = None) -> Host:
        """Create a Host object for the local machine."""
        host_id = self.host_id
        pyinfra_host = self._create_local_pyinfra_host()
        connector = PyinfraConnector(pyinfra_host)

        if tags is not None:
            self._save_tags(tags)

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
        lifecycle: HostLifecycleOptions | None = None,
        known_hosts: Sequence[str] | None = None,
    ) -> Host:
        """Create (or return) the local host.

        For the local provider, this always returns the same host representing
        the local computer. The name and image parameters are ignored since
        the local host is always the same machine. The known_hosts parameter
        is also ignored since the local machine uses its own known_hosts file.
        """
        with log_span("Creating local host (provider={})", self.name):
            host = self._create_host(name, tags)

            # Record BOOT activity for consistency. In this case it represents when mngr first created the local host
            host.record_activity(ActivitySource.BOOT)

        return host

    def stop_host(
        self,
        host: HostInterface | HostId,
        create_snapshot: bool = True,
        timeout_seconds: float = 60.0,
    ) -> None:
        """Stop the host.

        Always raises LocalHostNotStoppableError because the local computer
        cannot be stopped by mngr.
        """
        raise LocalHostNotStoppableError()

    def start_host(
        self,
        host: HostInterface | HostId,
        snapshot_id: SnapshotId | None = None,
    ) -> Host:
        """Start the host.

        For the local provider, this simply returns the local host since it
        is always running.
        """
        local_host = self._create_host(HostName("local"))

        return local_host

    def destroy_host(self, host: HostInterface | HostId) -> None:
        """Destroy the host.

        Always raises LocalHostNotDestroyableError because the local computer
        cannot be destroyed by mngr.
        """
        raise LocalHostNotDestroyableError()

    def delete_host(self, host: HostInterface) -> None:
        raise Exception("delete_host should not be called for LocalProviderInstance since hosts are never offline")

    def on_connection_error(self, host_id: HostId) -> None:
        pass

    # =========================================================================
    # Discovery Methods
    # =========================================================================

    def get_host(
        self,
        host: HostId | HostName,
    ) -> Host:
        """Get the local host by ID or name.

        For the local provider, this always returns the same host if the ID
        matches, or raises HostNotFoundError if it doesn't match.
        """
        host_id = self.host_id

        if isinstance(host, HostId):
            if host != host_id:
                logger.trace("Failed to find host with id={} (local host id={})", host, host_id)
                raise HostNotFoundError(host)
        # For HostName, we accept "local" or any name since there's only one host

        return self._create_host(HostName("local"))

    def list_hosts(
        self,
        cg: ConcurrencyGroup,
        include_destroyed: bool = False,
    ) -> list[HostInterface]:
        """List all hosts managed by this provider.

        For the local provider, this always returns a single-element list
        containing the local host.
        """
        hosts = [self._create_host(HostName("local"))]
        logger.trace("Listed hosts for local provider {}", self.name)
        return hosts

    # =========================================================================
    # Snapshot Methods
    # =========================================================================

    def create_snapshot(
        self,
        host: HostInterface | HostId,
        name: SnapshotName | None = None,
    ) -> SnapshotId:
        """Create a snapshot.

        Always raises SnapshotsNotSupportedError because the local provider
        does not support snapshots.
        """
        raise SnapshotsNotSupportedError(self.name)

    def list_snapshots(
        self,
        host: HostInterface | HostId,
    ) -> list[SnapshotInfo]:
        """List snapshots for a host.

        Always returns an empty list because the local provider does not
        support snapshots.
        """
        return []

    def delete_snapshot(
        self,
        host: HostInterface | HostId,
        snapshot_id: SnapshotId,
    ) -> None:
        """Delete a snapshot.

        Always raises SnapshotsNotSupportedError because the local provider
        does not support snapshots.
        """
        raise SnapshotsNotSupportedError(self.name)

    # =========================================================================
    # Volume Methods
    # =========================================================================

    def list_volumes(self) -> list[VolumeInfo]:
        """List all local volumes (subdirectories of ~/.mngr/volumes/)."""
        volumes_dir = self._volumes_dir
        if not volumes_dir.is_dir():
            return []
        return []

    def delete_volume(self, volume_id: VolumeId) -> None:
        """Delete a local volume directory."""
        volumes_dir = self._volumes_dir
        # Volume directories are named by host_id
        for subdir in volumes_dir.iterdir():
            if subdir.is_dir() and subdir.name == str(volume_id):
                shutil.rmtree(subdir)
                logger.debug("Deleted local volume: {}", subdir)
                return
        raise FileNotFoundError(f"Volume {volume_id} not found in {volumes_dir}")

    def get_volume_for_host(self, host: HostInterface | HostId) -> Volume | None:
        """Get the local volume for a host.

        Returns a LocalVolume backed by ~/.mngr/volumes/{host_id}/.
        The directory is created if it doesn't exist.
        """
        host_id = host.id if isinstance(host, HostInterface) else host
        volume_dir = self._volumes_dir / str(host_id)
        volume_dir.mkdir(parents=True, exist_ok=True)
        return LocalVolume(root_path=volume_dir)

    # =========================================================================
    # Host Mutation Methods
    # =========================================================================

    def get_host_tags(
        self,
        host: HostInterface | HostId,
    ) -> dict[str, str]:
        """Get tags for the local host."""
        return self._load_tags()

    def set_host_tags(
        self,
        host: HostInterface | HostId,
        tags: Mapping[str, str],
    ) -> None:
        """Set tags for the local host."""
        self._save_tags(tags)
        logger.trace("Set {} tag(s) on local host", len(tags))

    def add_tags_to_host(
        self,
        host: HostInterface | HostId,
        tags: Mapping[str, str],
    ) -> None:
        """Add tags to the local host."""
        existing_tags = self._load_tags()
        existing_tags.update(tags)
        self._save_tags(existing_tags)
        logger.trace("Added {} tag(s) to local host", len(tags))

    def remove_tags_from_host(
        self,
        host: HostInterface | HostId,
        keys: Sequence[str],
    ) -> None:
        """Remove tags by key from the local host."""
        existing_tags = self._load_tags()
        keys_to_remove = set(keys)
        filtered_tags = {k: v for k, v in existing_tags.items() if k not in keys_to_remove}
        self._save_tags(filtered_tags)
        logger.trace("Removed {} tag(s) from local host", len(keys))

    def rename_host(
        self,
        host: HostInterface | HostId,
        name: HostName,
    ) -> Host:
        """Rename the local host.

        For the local provider, this is a no-op since the host name is always
        effectively "local". Returns the host unchanged.
        """
        return self._create_host(name)

    # =========================================================================
    # Connector Method
    # =========================================================================

    def get_connector(
        self,
        host: HostInterface | HostId,
    ) -> PyinfraHost:
        """Get the pyinfra connector for the local host."""
        return self._create_local_pyinfra_host()

    # =========================================================================
    # Resource Methods (used by Host)
    # =========================================================================

    def get_host_resources(self, host: HostInterface) -> HostResources:
        """Get resource information for the local host.

        Uses psutil for cross-platform compatibility when available.
        """
        # Get CPU count and frequency
        cpu_count = psutil.cpu_count(logical=True) or 1
        cpu_freq = psutil.cpu_freq() if hasattr(psutil, "cpu_freq") else None
        cpu_freq_ghz = cpu_freq.current / 1000 if cpu_freq else None

        # Get memory in GB
        memory = psutil.virtual_memory()
        memory_gb = memory.total / (1024**3)

        # Get disk space in GB (for root partition)
        try:
            disk = psutil.disk_usage("/")
            disk_gb = disk.total / (1024**3)
        except OSError:
            disk_gb = None

        return HostResources(
            cpu=CpuResources(count=cpu_count, frequency_ghz=cpu_freq_ghz),
            memory_gb=memory_gb,
            disk_gb=disk_gb,
            gpu=None,
        )
