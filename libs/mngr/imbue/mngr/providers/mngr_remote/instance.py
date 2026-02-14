from collections.abc import Mapping
from collections.abc import Sequence

from loguru import logger
from pydantic import Field
from pydantic import SecretStr
from pyinfra.api.host import Host as PyinfraHost

from imbue.concurrency_group.concurrency_group import ConcurrencyGroup
from imbue.mngr.api.data_types import HostLifecycleOptions
from imbue.mngr.errors import ProviderError
from imbue.mngr.hosts.host import Host
from imbue.mngr.interfaces.data_types import HostResources
from imbue.mngr.interfaces.data_types import SnapshotInfo
from imbue.mngr.interfaces.data_types import VolumeInfo
from imbue.mngr.interfaces.host import HostInterface
from imbue.mngr.primitives import HostId
from imbue.mngr.primitives import HostName
from imbue.mngr.primitives import ImageReference
from imbue.mngr.primitives import SnapshotId
from imbue.mngr.primitives import SnapshotName
from imbue.mngr.primitives import VolumeId
from imbue.mngr.providers.base_provider import BaseProviderInstance
from imbue.mngr.providers.mngr_remote.client import MngrRemoteClient


class MngrRemoteProviderInstance(BaseProviderInstance):
    """Provider instance that proxies operations to a remote mngr API server.

    This allows `mngr list` on one machine to show agents managed by
    a remote mngr instance, without needing SSH keys or cloud credentials.

    Currently supports read-only operations (listing agents). Write operations
    should be performed through the remote mngr CLI or web UI.
    """

    remote_url: str = Field(frozen=True, description="Base URL of the remote mngr API server")
    remote_token: SecretStr = Field(frozen=True, description="Bearer token for the remote API server")

    def _get_client(self) -> MngrRemoteClient:
        """Create a client for the remote API server."""
        return MngrRemoteClient(base_url=self.remote_url, token=self.remote_token)

    @property
    def is_authorized(self) -> bool:
        return True

    @property
    def supports_snapshots(self) -> bool:
        return False

    @property
    def supports_shutdown_hosts(self) -> bool:
        return False

    @property
    def supports_volumes(self) -> bool:
        return False

    @property
    def supports_mutable_tags(self) -> bool:
        return False

    def list_hosts(
        self,
        cg: ConcurrencyGroup,
        include_destroyed: bool = False,
    ) -> list[HostInterface]:
        """List hosts from the remote API. Returns empty list since hosts are remote.

        Agent data is accessed via list_persisted_agent_data_for_host().
        """
        return []

    def list_persisted_agent_data_for_host(self, host_id: HostId) -> list[dict]:
        """Fetch agent data from the remote API server."""
        try:
            all_agents = self._get_client().list_agents()
            return [a for a in all_agents if a.get("host", {}).get("id") == str(host_id)]
        except ProviderError:
            return []

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
        raise ProviderError("Cannot create hosts through mngr remote provider. Use the remote mngr instance directly.")

    def stop_host(
        self,
        host: HostInterface | HostId,
        create_snapshot: bool = True,
        timeout_seconds: float = 60.0,
    ) -> None:
        raise ProviderError("Cannot stop hosts through mngr remote provider. Use the remote mngr instance directly.")

    def start_host(
        self,
        host: HostInterface | HostId,
        snapshot_id: SnapshotId | None = None,
    ) -> Host:
        raise ProviderError("Cannot start hosts through mngr remote provider. Use the remote mngr instance directly.")

    def destroy_host(
        self,
        host: HostInterface | HostId,
        delete_snapshots: bool = True,
    ) -> None:
        raise ProviderError(
            "Cannot destroy hosts through mngr remote provider. Use the remote mngr instance directly."
        )

    def on_connection_error(self, host_id: HostId) -> None:
        logger.debug("Connection error for remote host {}", host_id)

    def get_host(self, host: HostId | HostName) -> HostInterface:
        raise ProviderError("Cannot access individual hosts through mngr remote provider.")

    def get_host_resources(self, host: HostInterface) -> HostResources:
        raise ProviderError("Cannot query host resources through mngr remote provider.")

    def create_snapshot(self, host: HostInterface | HostId, name: SnapshotName | None = None) -> SnapshotId:
        raise ProviderError("Snapshots not supported through mngr remote provider.")

    def list_snapshots(self, host: HostInterface | HostId) -> list[SnapshotInfo]:
        return []

    def delete_snapshot(self, host: HostInterface | HostId, snapshot_id: SnapshotId) -> None:
        raise ProviderError("Snapshots not supported through mngr remote provider.")

    def list_volumes(self) -> list[VolumeInfo]:
        return []

    def delete_volume(self, volume_id: VolumeId) -> None:
        raise ProviderError("Volumes not supported through mngr remote provider.")

    def get_host_tags(self, host: HostInterface | HostId) -> dict[str, str]:
        return {}

    def set_host_tags(self, host: HostInterface | HostId, tags: Mapping[str, str]) -> None:
        raise ProviderError("Cannot set tags through mngr remote provider.")

    def add_tags_to_host(self, host: HostInterface | HostId, tags: Mapping[str, str]) -> None:
        raise ProviderError("Cannot set tags through mngr remote provider.")

    def remove_tags_from_host(self, host: HostInterface | HostId, keys: Sequence[str]) -> None:
        raise ProviderError("Cannot remove tags through mngr remote provider.")

    def rename_host(self, host: HostInterface | HostId, name: HostName) -> HostInterface:
        raise ProviderError("Cannot rename hosts through mngr remote provider.")

    def get_connector(self, host: HostInterface | HostId) -> PyinfraHost:
        raise ProviderError("Cannot get connectors through mngr remote provider.")
